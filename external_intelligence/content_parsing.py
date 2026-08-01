"""Parsers for official report metadata and public YouTube Atom feeds."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from external_intelligence.content_models import parse_youtube_video_id

_TAG_PATTERN = re.compile(r"<[^>]+>")
_SPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class ReportMetadata:
    """Source metadata for one official publication or data report."""

    title: str
    summary: str
    source_url: str
    document_url: str
    published_at: datetime
    topics: tuple[str, ...]
    thumbnail_url: str | None = None


@dataclass(frozen=True)
class VideoMetadata:
    """Metadata exposed by one public YouTube channel feed entry."""

    title: str
    summary: str
    source_url: str
    published_at: datetime
    video_id: str
    thumbnail_url: str | None


class _ReportPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, list[str]] = {}
        self.links: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "meta":
            key = (values.get("property") or values.get("name") or "").casefold()
            content = values.get("content", "").strip()
            if key and content:
                self.metadata.setdefault(key, []).append(content)
        elif tag.casefold() == "a" and values.get("href"):
            self.links.append(values["href"])


def parse_govdata_reports(document: bytes) -> tuple[ReportMetadata, ...]:
    """Parse real CKAN package metadata returned by GovData."""

    payload = json.loads(document.decode("utf-8"))
    result = payload.get("result") if isinstance(payload, dict) else None
    packages = result.get("results") if isinstance(result, dict) else None
    if not isinstance(packages, list):
        raise ValueError("GovData response does not contain package results")
    reports: list[ReportMetadata] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = _clean(str(package.get("name") or ""))
        title = _clean(str(package.get("title") or ""))
        summary = _clean(str(package.get("notes") or title))
        published = _date(str(package.get("metadata_modified") or ""))
        document_url = _document_url(package.get("resources"))
        if not name or not title or published is None or document_url is None:
            continue
        reports.append(
            ReportMetadata(
                title=title,
                summary=summary or title,
                source_url=f"https://www.govdata.de/suche/daten/{name}",
                document_url=document_url,
                published_at=published,
                topics=("KBA", "new registrations", "official data"),
                thumbnail_url=None,
            )
        )
    return tuple(sorted(reports, key=lambda item: item.published_at, reverse=True))


def parse_official_report_page(
    document: bytes,
    *,
    page_url: str,
) -> ReportMetadata | None:
    """Read OpenGraph/article metadata and a real PDF link from an official page."""

    parser = _ReportPageParser()
    parser.feed(document.decode("utf-8", errors="replace"))
    title = _first(parser.metadata, "og:title")
    summary = _first(parser.metadata, "og:description", "description")
    published = _date(
        _first(
            parser.metadata,
            "article:published_time",
            "og:publish_date",
        )
    )
    if not title or not summary or published is None:
        return None
    pdf_links = [
        urljoin(page_url, value)
        for value in parser.links
        if urlparse(urljoin(page_url, value)).path.casefold().endswith(".pdf")
    ]
    thumbnail = _first(parser.metadata, "og:image") or None
    if thumbnail and not thumbnail.startswith("https://"):
        thumbnail = None
    topics = tuple(
        sorted(
            {
                _clean(value)
                for value in parser.metadata.get("article:tag", [])
                if _clean(value)
            }
        )
    )
    return ReportMetadata(
        title=_clean(title),
        summary=_clean(summary),
        source_url=page_url,
        document_url=pdf_links[0] if pdf_links else page_url,
        published_at=published,
        topics=topics,
        thumbnail_url=thumbnail,
    )


def parse_youtube_feed(document: bytes) -> tuple[VideoMetadata, ...]:
    """Parse public YouTube Atom metadata without downloading video media."""

    root = ElementTree.fromstring(document)
    videos: list[VideoMetadata] = []
    for entry in (item for item in root.iter() if _local(item.tag) == "entry"):
        title = _child_text(entry, "title")
        published = _date(_child_text(entry, "published"))
        video_id = _child_text(entry, "videoId")
        source_url = _entry_link(entry)
        summary = _child_text(entry, "description") or title
        thumbnail_url = _thumbnail(entry)
        if (
            not title
            or published is None
            or parse_youtube_video_id(source_url) != video_id
        ):
            continue
        videos.append(
            VideoMetadata(
                title=_clean(title),
                summary=_clean(summary),
                source_url=source_url,
                published_at=published,
                video_id=video_id,
                thumbnail_url=thumbnail_url,
            )
        )
    return tuple(sorted(videos, key=lambda item: item.published_at, reverse=True))


def _document_url(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    ranked: list[tuple[int, str]] = []
    for resource in value:
        if not isinstance(resource, dict):
            continue
        url = str(resource.get("url") or "").strip()
        if not url.startswith("https://"):
            continue
        file_format = str(resource.get("format") or "").casefold()
        priority = 0 if file_format == "pdf" else 1
        ranked.append((priority, url))
    return min(ranked)[1] if ranked else None


def _first(metadata: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = metadata.get(key, [])
        if values:
            return values[0].strip()
    return ""


def _entry_link(entry: ElementTree.Element) -> str:
    for element in entry:
        if _local(element.tag) == "link" and element.attrib.get("rel") == "alternate":
            return str(element.attrib.get("href") or "").strip()
    return ""


def _thumbnail(entry: ElementTree.Element) -> str | None:
    for element in entry.iter():
        if _local(element.tag) == "thumbnail":
            url = str(element.attrib.get("url") or "").strip()
            return url if url.startswith("https://") else None
    return None


def _child_text(entry: ElementTree.Element, name: str) -> str:
    for element in entry.iter():
        if _local(element.tag) == name and element.text:
            return element.text.strip()
    return ""


def _local(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _date(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _clean(value: str) -> str:
    text = html.unescape(_TAG_PATTERN.sub(" ", value))
    return _SPACE_PATTERN.sub(" ", text).strip()[:600]
