"""Atomic filesystem TTL cache for external public resources."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from external_intelligence.http import HTTPFetcher


@dataclass(frozen=True)
class CacheEntry:
    """One cached payload and its provenance metadata."""

    source_id: str
    source_url: str
    payload_path: Path
    fetched_at: datetime
    expires_at: datetime
    content_type: str
    sha256: str
    cache_status: str


class ExternalIntelligenceCache:
    """Cache downloaded bytes by source and URL with stale-on-error support."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).expanduser().resolve(strict=False)

    def get_or_fetch(
        self,
        *,
        source_id: str,
        source_url: str,
        ttl_seconds: int,
        fetcher: HTTPFetcher,
        now: datetime | None = None,
    ) -> CacheEntry:
        """Return a fresh entry, refresh it, or fall back to a stale payload."""

        if not source_id.strip() or ttl_seconds <= 0:
            raise ValueError("cache source_id and positive TTL are required")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        paths = self._paths(source_id, source_url)
        existing = self._read_existing(*paths)
        if existing is not None and existing.expires_at > current:
            return _with_status(existing, "hit")

        conditional_headers: dict[str, str] = {}
        metadata = self._read_metadata(paths[1])
        if metadata is not None:
            if metadata.get("etag"):
                conditional_headers["If-None-Match"] = str(metadata["etag"])
            if metadata.get("last_modified"):
                conditional_headers["If-Modified-Since"] = str(
                    metadata["last_modified"]
                )
        try:
            response = fetcher.fetch(source_url, headers=conditional_headers)
            if response.status_code == 304 and existing is not None:
                return self._refresh_metadata(
                    existing,
                    metadata or {},
                    paths[1],
                    current,
                    ttl_seconds,
                )
            if response.status_code < 200 or response.status_code >= 300:
                raise ValueError(f"unexpected HTTP status {response.status_code}")
            return self._write_entry(
                source_id=source_id,
                source_url=source_url,
                payload_path=paths[0],
                metadata_path=paths[1],
                body=response.body,
                content_type=response.content_type,
                fetched_at=current,
                ttl_seconds=ttl_seconds,
                etag=response.etag,
                last_modified=response.last_modified,
            )
        except Exception:
            if existing is not None:
                return _with_status(existing, "stale_fallback")
            raise

    def _paths(self, source_id: str, source_url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(f"{source_id}\0{source_url}".encode()).hexdigest()
        source_suffix = Path(urlparse(source_url).path).suffix.casefold()
        payload_suffix = (
            source_suffix
            if source_suffix in {".xlsx", ".xml", ".rss", ".atom", ".html"}
            else ".payload"
        )
        return self.directory / f"{key}{payload_suffix}", self.directory / f"{key}.json"

    def _read_existing(
        self,
        payload_path: Path,
        metadata_path: Path,
    ) -> CacheEntry | None:
        metadata = self._read_metadata(metadata_path)
        if metadata is None or not payload_path.is_file():
            return None
        body_hash = hashlib.sha256(payload_path.read_bytes()).hexdigest()
        if body_hash != metadata.get("sha256"):
            return None
        try:
            return CacheEntry(
                source_id=str(metadata["source_id"]),
                source_url=str(metadata["source_url"]),
                payload_path=payload_path,
                fetched_at=datetime.fromisoformat(str(metadata["fetched_at"])),
                expires_at=datetime.fromisoformat(str(metadata["expires_at"])),
                content_type=str(metadata.get("content_type", "")),
                sha256=body_hash,
                cache_status="hit",
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _read_metadata(path: Path) -> dict[str, object] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_entry(
        self,
        *,
        source_id: str,
        source_url: str,
        payload_path: Path,
        metadata_path: Path,
        body: bytes,
        content_type: str,
        fetched_at: datetime,
        ttl_seconds: int,
        etag: str | None,
        last_modified: str | None,
    ) -> CacheEntry:
        self.directory.mkdir(parents=True, exist_ok=True)
        expires_at = fetched_at + timedelta(seconds=ttl_seconds)
        digest = hashlib.sha256(body).hexdigest()
        metadata = {
            "source_id": source_id,
            "source_url": source_url,
            "fetched_at": fetched_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "content_type": content_type,
            "sha256": digest,
            "etag": etag,
            "last_modified": last_modified,
        }
        _atomic_write_bytes(payload_path, body)
        _atomic_write_text(
            metadata_path,
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        )
        return CacheEntry(
            source_id=source_id,
            source_url=source_url,
            payload_path=payload_path,
            fetched_at=fetched_at,
            expires_at=expires_at,
            content_type=content_type,
            sha256=digest,
            cache_status="refreshed",
        )

    def _refresh_metadata(
        self,
        existing: CacheEntry,
        metadata: dict[str, object],
        metadata_path: Path,
        current: datetime,
        ttl_seconds: int,
    ) -> CacheEntry:
        expires_at = current + timedelta(seconds=ttl_seconds)
        metadata.update(
            fetched_at=current.isoformat(),
            expires_at=expires_at.isoformat(),
        )
        _atomic_write_text(
            metadata_path,
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        )
        return CacheEntry(
            source_id=existing.source_id,
            source_url=existing.source_url,
            payload_path=existing.payload_path,
            fetched_at=current,
            expires_at=expires_at,
            content_type=existing.content_type,
            sha256=existing.sha256,
            cache_status="revalidated",
        )


def _with_status(entry: CacheEntry, status: str) -> CacheEntry:
    return CacheEntry(**{**entry.__dict__, "cache_status": status})


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
