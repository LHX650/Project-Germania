"""Validated models for the public automotive content feed."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import parse_qs, urlparse


class ContentType(StrEnum):
    """Content categories displayed by the intelligence hub."""

    NEWS = "news"
    REPORT = "report"
    VIDEO = "video"


class ImpactLevel(StrEnum):
    """Transparent relevance level derived from entity recognition."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ContentItem:
    """One source-attributed content item with no copied article body."""

    content_id: str
    content_type: ContentType
    title: str
    source_name: str
    source_url: str
    published_at: datetime
    summary: str
    language: str
    region: str
    brands: tuple[str, ...]
    vehicles: tuple[str, ...]
    topics: tuple[str, ...]
    impact_level: ImpactLevel
    thumbnail_url: str | None
    document_url: str | None
    video_id: str | None
    collected_at: datetime
    evidence_status: str
    ai_summary: str | None = None
    summary_mode: str = "source_metadata"

    def __post_init__(self) -> None:
        """Reject malformed evidence before it can enter the feed."""

        for field_name in ("content_id", "title", "source_name", "summary"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be non-empty")
        _require_https(self.source_url, "source_url")
        if self.thumbnail_url is not None:
            _require_https(self.thumbnail_url, "thumbnail_url")
        if self.document_url is not None:
            _require_https(self.document_url, "document_url")
        if self.published_at.tzinfo is None or self.collected_at.tzinfo is None:
            raise ValueError("content timestamps must be timezone-aware")
        if self.published_at.astimezone(UTC) > self.collected_at.astimezone(UTC):
            raise ValueError("published_at cannot be later than collected_at")
        if self.content_type is ContentType.REPORT and self.document_url is None:
            raise ValueError("report content requires document_url")
        if self.content_type is ContentType.VIDEO:
            parsed_id = parse_youtube_video_id(self.source_url)
            if not self.video_id or parsed_id != self.video_id:
                raise ValueError("video content requires a matching YouTube video_id")
        elif self.video_id is not None:
            raise ValueError("video_id is only valid for video content")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        payload = asdict(self)
        payload["content_type"] = self.content_type.value
        payload["impact_level"] = self.impact_level.value
        payload["published_at"] = self.published_at.astimezone(UTC).isoformat()
        payload["collected_at"] = self.collected_at.astimezone(UTC).isoformat()
        for field_name in ("brands", "vehicles", "topics"):
            payload[field_name] = list(payload[field_name])
        return payload


def content_id(content_type: ContentType, source_url: str) -> str:
    """Create a stable ID from the type and canonical public URL."""

    canonical = canonical_url(source_url)
    return hashlib.sha256(f"{content_type.value}\0{canonical}".encode()).hexdigest()[
        :24
    ]


def canonical_url(value: str) -> str:
    """Normalize a public URL for evidence and duplicate checks."""

    _require_https(value, "URL")
    parsed = urlparse(value.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    retained = {
        key: values
        for key, values in query.items()
        if not key.casefold().startswith("utm_") and key.casefold() != "feature"
    }
    pairs = sorted((key, value) for key, values in retained.items() for value in values)
    query_text = "&".join(f"{key}={value}" for key, value in pairs)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(
        scheme="https",
        netloc=parsed.netloc.casefold(),
        path=path,
        query=query_text,
        fragment="",
    ).geturl()


def parse_youtube_video_id(value: str) -> str | None:
    """Extract a valid YouTube ID from watch, short, or embed URLs."""

    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return None
    host = parsed.netloc.casefold().split(":", 1)[0]
    video_id: str | None = None
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        segments = [segment for segment in parsed.path.split("/") if segment]
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif len(segments) >= 2 and segments[0] in {"embed", "shorts", "live"}:
            video_id = segments[1]
    if (
        video_id
        and len(video_id) == 11
        and all(character.isalnum() or character in "-_" for character in video_id)
    ):
        return video_id
    return None


def _require_https(value: str, field_name: str) -> None:
    parsed = urlparse(str(value).strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute HTTPS URL")
