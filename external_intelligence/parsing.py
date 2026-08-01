"""RSS/Atom and structured NewsArticle parsing with source preservation."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin
from xml.etree import ElementTree

from external_intelligence.models import NewsArticle
from external_intelligence.recognition import recognize_entities

_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_SPACE_PATTERN = re.compile(r"\s+")
_VISIBLE_DATE_PATTERN = re.compile(
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}|"
    r"\d{1,2}[./]\d{1,2}[./](?:\d{2}|\d{4})",
    re.IGNORECASE,
)


class _DiscoveryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.feed_links: list[str] = []
        self.json_ld: list[str] = []
        self._in_json_ld = False
        self._buffer: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "link":
            rel = values.get("rel", "").casefold().split()
            content_type = values.get("type", "").casefold()
            if (
                "alternate" in rel
                and content_type
                in {
                    "application/rss+xml",
                    "application/atom+xml",
                }
                and values.get("href")
            ):
                self.feed_links.append(values["href"])
        if (
            tag.casefold() == "script"
            and values.get("type", "").casefold() == "application/ld+json"
        ):
            self._in_json_ld = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._buffer))
            self._in_json_ld = False
            self._buffer = []


class _SemanticArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.articles: list[dict[str, object]] = []
        self._active = False
        self._heading_level = 0
        self._paragraph_level = 0
        self._heading_link: str | None = None
        self._headings: list[str] = []
        self._paragraphs: list[str] = []
        self._all_text: list[str] = []
        self._published: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        name = tag.casefold()
        if name == "article" and not self._active:
            self._active = True
            self._reset()
        if not self._active:
            return
        if name in {"h1", "h2", "h3", "h4"}:
            self._heading_level += 1
        elif name == "p":
            self._paragraph_level += 1
        elif name == "a" and self._heading_level and values.get("href"):
            self._heading_link = values["href"]
        elif name == "time" and values.get("datetime"):
            self._published = values["datetime"]

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if not self._active:
            return
        if name in {"h1", "h2", "h3", "h4"} and self._heading_level:
            self._heading_level -= 1
        elif name == "p" and self._paragraph_level:
            self._paragraph_level -= 1
        elif name == "article":
            self.articles.append(
                {
                    "title": _clean_text(" ".join(self._headings)),
                    "summary": _clean_text(" ".join(self._paragraphs)),
                    "text": _clean_text(" ".join(self._all_text)),
                    "url": self._heading_link,
                    "published": self._published,
                }
            )
            self._active = False

    def handle_data(self, data: str) -> None:
        if not self._active:
            return
        text = data.strip()
        if not text:
            return
        self._all_text.append(text)
        if self._heading_level:
            self._headings.append(text)
        elif self._paragraph_level:
            self._paragraphs.append(text)

    def _reset(self) -> None:
        self._heading_level = 0
        self._paragraph_level = 0
        self._heading_link = None
        self._headings = []
        self._paragraphs = []
        self._all_text = []
        self._published = None


def discover_feed_url(document: bytes, page_url: str) -> str | None:
    """Return the first RSS/Atom autodiscovery URL from an official page."""

    parser = _DiscoveryParser()
    parser.feed(document.decode("utf-8", errors="replace"))
    return urljoin(page_url, parser.feed_links[0]) if parser.feed_links else None


def parse_feed(
    document: bytes,
    *,
    source: str,
    source_url: str,
    country: str,
    tracked_brands: tuple[str, ...],
    tracked_vehicles: tuple[str, ...],
    source_brand: str | None,
    official_brand_news: bool,
) -> tuple[NewsArticle, ...]:
    """Parse RSS 2.0 or Atom entries into a unified article schema."""

    root = ElementTree.fromstring(document)
    entries = [
        element
        for element in root.iter()
        if _local_name(element.tag) in {"item", "entry"}
    ]
    articles = []
    for entry in entries:
        title = _child_text(entry, "title")
        url = _entry_url(entry)
        published = _parse_date(
            _child_text(entry, "published", "updated", "pubDate", "date")
        )
        if not title or not url or published is None:
            continue
        summary = _clean_text(
            _child_text(entry, "summary", "description", "content") or title
        )
        categories = tuple(
            sorted(
                {
                    value
                    for element in entry.iter()
                    if _local_name(element.tag) == "category"
                    for value in (
                        (element.attrib.get("term") or element.text or "").strip(),
                    )
                    if value
                }
            )
        )
        text = f"{title} {summary} {' '.join(categories)}"
        brands, models = recognize_entities(
            text,
            tracked_brands=tracked_brands,
            tracked_vehicles=tracked_vehicles,
            source_brand=source_brand,
        )
        articles.append(
            NewsArticle(
                article_id=_article_id(source, url),
                title=_clean_text(title),
                summary=summary,
                url=url,
                source=source,
                source_url=source_url,
                published_at=published,
                brands=brands,
                models=models,
                country=country,
                tags=categories,
                official_brand_news=official_brand_news,
            )
        )
    return _deduplicate(articles)


def parse_structured_news(
    document: bytes,
    *,
    source: str,
    source_url: str,
    country: str,
    tracked_brands: tuple[str, ...],
    tracked_vehicles: tuple[str, ...],
    source_brand: str | None,
    official_brand_news: bool,
) -> tuple[NewsArticle, ...]:
    """Parse JSON-LD NewsArticle objects when an RSS feed is unavailable."""

    parser = _DiscoveryParser()
    parser.feed(document.decode("utf-8", errors="replace"))
    objects: list[dict[str, object]] = []
    for block in parser.json_ld:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        objects.extend(_news_objects(payload))
    articles = []
    for item in objects:
        title = str(item.get("headline") or item.get("name") or "").strip()
        url = _json_url(item.get("url"), source_url)
        published = _parse_date(str(item.get("datePublished") or ""))
        if not title or not url or published is None:
            continue
        summary = _clean_text(str(item.get("description") or title))
        keywords = item.get("keywords")
        if isinstance(keywords, list):
            tags = tuple(sorted(str(value).strip() for value in keywords if value))
        elif isinstance(keywords, str):
            tags = tuple(
                sorted(value.strip() for value in keywords.split(",") if value.strip())
            )
        else:
            tags = ()
        brands, models = recognize_entities(
            f"{title} {summary} {' '.join(tags)}",
            tracked_brands=tracked_brands,
            tracked_vehicles=tracked_vehicles,
            source_brand=source_brand,
        )
        articles.append(
            NewsArticle(
                article_id=_article_id(source, url),
                title=_clean_text(title),
                summary=summary,
                url=url,
                source=source,
                source_url=source_url,
                published_at=published,
                brands=brands,
                models=models,
                country=country,
                tags=tags,
                official_brand_news=official_brand_news,
            )
        )
    return _deduplicate(articles)


def parse_semantic_html_news(
    document: bytes,
    *,
    source: str,
    source_url: str,
    country: str,
    tracked_brands: tuple[str, ...],
    tracked_vehicles: tuple[str, ...],
    source_brand: str | None,
    official_brand_news: bool,
) -> tuple[NewsArticle, ...]:
    """Parse dated semantic HTML article cards when feeds are unavailable."""

    parser = _SemanticArticleParser()
    parser.feed(document.decode("utf-8", errors="replace"))
    articles = []
    for item in parser.articles:
        title = str(item["title"]).strip()
        text = str(item["text"])
        url = urljoin(source_url, str(item.get("url") or ""))
        published_text = str(item.get("published") or "")
        if not published_text:
            date_match = _VISIBLE_DATE_PATTERN.search(text)
            published_text = date_match.group(0) if date_match else ""
        published = _parse_date(published_text)
        if not title or not url or published is None:
            continue
        summary = str(item["summary"]).strip() or title
        brands, models = recognize_entities(
            f"{title} {summary}",
            tracked_brands=tracked_brands,
            tracked_vehicles=tracked_vehicles,
            source_brand=source_brand,
        )
        articles.append(
            NewsArticle(
                article_id=_article_id(source, url),
                title=title,
                summary=summary,
                url=url,
                source=source,
                source_url=source_url,
                published_at=published,
                brands=brands,
                models=models,
                country=country,
                tags=(),
                official_brand_news=official_brand_news,
            )
        )
    return _deduplicate(articles)


def _news_objects(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for entry in value for item in _news_objects(entry)]
    if not isinstance(value, dict):
        return []
    type_value = value.get("@type")
    types = {type_value} if isinstance(type_value, str) else set(type_value or [])
    found = [value] if types & {"NewsArticle", "Article", "PressRelease"} else []
    for key in ("@graph", "itemListElement", "item"):
        found.extend(_news_objects(value.get(key)))
    return found


def _entry_url(entry: ElementTree.Element) -> str:
    for element in entry:
        if _local_name(element.tag) != "link":
            continue
        href = (element.attrib.get("href") or "").strip()
        rel = element.attrib.get("rel", "alternate")
        if href and rel == "alternate":
            return href
        if element.text and element.text.strip():
            return element.text.strip()
    return _child_text(entry, "guid", "id")


def _child_text(entry: ElementTree.Element, *names: str) -> str:
    accepted = set(names)
    for element in entry.iter():
        if _local_name(element.tag) in accepted and element.text:
            return element.text.strip()
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_date(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = _parse_visible_date(text)
            if parsed is None:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_visible_date(value: str) -> datetime | None:
    for date_format in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _clean_text(value: str) -> str:
    return _SPACE_PATTERN.sub(
        " ", html.unescape(_HTML_TAG_PATTERN.sub(" ", value))
    ).strip()


def _json_url(value: object, base_url: str) -> str:
    if isinstance(value, dict):
        value = value.get("@id")
    return urljoin(base_url, str(value).strip()) if value else ""


def _article_id(source: str, url: str) -> str:
    return hashlib.sha256(f"{source}\0{url}".encode()).hexdigest()[:24]


def _deduplicate(articles: list[NewsArticle]) -> tuple[NewsArticle, ...]:
    by_id = {article.article_id: article for article in articles}
    return tuple(
        sorted(by_id.values(), key=lambda item: item.published_at, reverse=True)
    )
