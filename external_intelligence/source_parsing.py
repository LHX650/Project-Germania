"""Bounded parsers for official newsrooms without standard feeds or markup."""

from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from external_intelligence.models import NewsArticle
from external_intelligence.parsing import parse_publication_date
from external_intelligence.recognition import recognize_entities

_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_SPACE_PATTERN = re.compile(r"\s+")


class _OfficialCardParser(HTMLParser):
    """Extract linked Mercedes-Benz and MG newsroom cards by semantic classes."""

    def __init__(self, source_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_id = source_id
        self.cards: list[dict[str, str]] = []
        self._active: dict[str, list[str] | str] | None = None
        self._field: str | None = None
        self._field_tag: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        name = tag.casefold()
        if name == "a" and self._active is None:
            href = values.get("href", "")
            if self._accept_link(href):
                self._active = {
                    "url": href,
                    "title": [],
                    "summary": [],
                    "published": [],
                    "image_url": "",
                }
        if self._active is None:
            return
        classes = values.get("class", "").casefold().split()
        field = self._field_for(name, classes)
        if field is not None:
            self._field = field
            self._field_tag = name
        if name in {"img", "source"} and not self._active["image_url"]:
            image_value = values.get("src") or values.get("srcset", "")
            self._active["image_url"] = image_value.split()[0]

    def handle_data(self, data: str) -> None:
        if self._active is None or self._field is None:
            return
        value = data.strip()
        if value:
            target = self._active[self._field]
            if isinstance(target, list):
                target.append(value)

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if self._active is None:
            return
        if name == "a":
            self.cards.append(
                {
                    key: _clean(" ".join(value) if isinstance(value, list) else value)
                    for key, value in self._active.items()
                }
            )
            self._active = None
            self._field = None
            self._field_tag = None
            return
        if name == self._field_tag:
            self._field = None
            self._field_tag = None

    def _accept_link(self, href: str) -> bool:
        if self.source_id == "mercedes_official_news":
            return bool(re.fullmatch(r"/(?:en/)?article/[0-9a-f-]+", href))
        if self.source_id == "mg_official_news":
            path = urlparse(href).path
            return "/press/" in path and path.rstrip("/") != "/press"
        return False

    def _field_for(self, tag: str, classes: list[str]) -> str | None:
        if self.source_id == "mercedes_official_news":
            if "topline" in classes:
                return "published"
            if tag in {"h2", "h3"} and "headline" in classes:
                return "title"
            if "fuel-label" in classes:
                return "summary"
        elif self.source_id == "mg_official_news":
            if "date" in classes:
                return "published"
            if tag == "h3":
                return "title"
            if tag == "p":
                return "summary"
        return None


class _ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self._active = False
        self._buffer: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.casefold() == "script":
            self._active = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._active:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._active:
            self.scripts.append("".join(self._buffer))
            self._active = False
            self._buffer = []


class _BMWArticleParser(HTMLParser):
    """Extract PressClub newsfeed cards without merging metadata into titles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, str]] = []
        self._active: dict[str, list[str] | str] | None = None
        self._field: str | None = None
        self._field_tag: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        name = tag.casefold()
        classes = values.get("class", "").casefold().split()
        if name == "article" and self._active is None and "newsfeed" in classes:
            self._active = {
                "url": "",
                "title": [],
                "summary": [],
                "published": [],
                "image_url": "",
            }
        if self._active is None:
            return
        if name == "h3":
            self._field, self._field_tag = "title", name
        elif name == "span" and "date" in classes:
            self._field, self._field_tag = "published", name
        elif name == "p" and "serif" in classes:
            self._field, self._field_tag = "summary", name
        elif name == "a" and self._field == "title" and values.get("href"):
            self._active["url"] = values["href"]
        if not self._active["image_url"] and (style := values.get("style")):
            match = re.search(r"background-image\s*:\s*url\(['\"]?([^)'\"]+)", style)
            if match is not None:
                self._active["image_url"] = match.group(1)

    def handle_data(self, data: str) -> None:
        if self._active is None or self._field is None:
            return
        value = data.strip()
        target = self._active[self._field]
        if value and isinstance(target, list):
            target.append(value)

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if self._active is None:
            return
        if name == "article":
            self.cards.append(
                {
                    key: _clean(" ".join(value) if isinstance(value, list) else value)
                    for key, value in self._active.items()
                }
            )
            self._active = None
            self._field = None
            self._field_tag = None
        elif name == self._field_tag:
            self._field = None
            self._field_tag = None


def parse_source_specific_news(
    document: bytes,
    *,
    source_id: str,
    source: str,
    source_url: str,
    country: str,
    tracked_brands: tuple[str, ...],
    tracked_vehicles: tuple[str, ...],
    source_brand: str | None,
    official_brand_news: bool,
) -> tuple[NewsArticle, ...]:
    """Parse only recognized official source layouts; return empty otherwise."""

    common = {
        "source": source,
        "source_url": source_url,
        "country": country,
        "tracked_brands": tracked_brands,
        "tracked_vehicles": tracked_vehicles,
        "source_brand": source_brand,
        "official_brand_news": official_brand_news,
    }
    if source_id == "mercedes_official_news" and document.lstrip().startswith(b"{"):
        return _mercedes_api_articles(document, **common)
    if source_id == "bmw_official_news":
        parser = _BMWArticleParser()
        parser.feed(document.decode("utf-8", errors="replace"))
        return _card_articles(parser.cards, **common)
    if source_id in {"mercedes_official_news", "mg_official_news"}:
        parser = _OfficialCardParser(source_id)
        parser.feed(document.decode("utf-8", errors="replace"))
        return _card_articles(parser.cards, **common)
    if source_id == "xpeng_official_news":
        return _xpeng_articles(document, **common)
    if source_id in {"vda_news", "vda_automotive_news"}:
        return _vda_articles(document, **common)
    return ()


def _card_articles(
    cards: list[dict[str, str]],
    **common: object,
) -> tuple[NewsArticle, ...]:
    articles = []
    for card in cards:
        article = _article(
            title=card["title"],
            summary=card["summary"] or card["title"],
            url=urljoin(str(common["source_url"]), card["url"]),
            published=card["published"],
            image_url=card["image_url"],
            tags=(),
            **common,
        )
        if article is not None:
            articles.append(article)
    return _deduplicate(articles)


def _xpeng_articles(document: bytes, **common: object) -> tuple[NewsArticle, ...]:
    parser = _ScriptParser()
    parser.feed(document.decode("utf-8", errors="replace"))
    records: list[dict[str, object]] = []
    for script in parser.scripts:
        prefix = "self.__next_f.push("
        if not script.startswith(prefix) or not script.endswith(")"):
            continue
        try:
            wrapper = json.loads(script[len(prefix) : -1])
        except json.JSONDecodeError:
            continue
        if not isinstance(wrapper, list) or len(wrapper) < 2:
            continue
        payload = wrapper[1]
        if not isinstance(payload, str) or ":" not in payload:
            continue
        try:
            value = json.loads(payload.split(":", 1)[1])
        except json.JSONDecodeError:
            continue
        records.extend(_walk_news_records(value))
    articles = []
    for item in records:
        article_id = str(item.get("id") or "").strip()
        article = _article(
            title=str(item.get("title") or ""),
            summary=str(item.get("subTitle") or item.get("seoDescription") or ""),
            url=urljoin(
                str(common["source_url"]),
                f"/pressroom/news/{article_id}",
            ),
            published=str(item.get("date") or ""),
            image_url=str(item.get("coverUrl") or ""),
            tags=tuple(
                value
                for key in ("regionCode", "langCode")
                if (value := str(item.get(key) or "").strip())
            ),
            **common,
        )
        if article_id and article is not None:
            articles.append(article)
    return _deduplicate(articles)


def _walk_news_records(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [record for item in value for record in _walk_news_records(item)]
    if not isinstance(value, dict):
        return []
    found = []
    if {"id", "title", "date"}.issubset(value):
        found.append(value)
    for item in value.values():
        found.extend(_walk_news_records(item))
    return found


def _vda_articles(document: bytes, **common: object) -> tuple[NewsArticle, ...]:
    try:
        payload = json.loads(document.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return ()
    articles = []
    for item in payload["items"]:
        if not isinstance(item, dict):
            continue
        article = _article(
            title=str(item.get("title") or ""),
            summary=str(item.get("text") or item.get("title") or ""),
            url=urljoin(str(common["source_url"]), str(item.get("path") or "")),
            published=str(item.get("date") or ""),
            image_url="",
            tags=tuple([str(item["location"]).strip()] if item.get("location") else []),
            **common,
        )
        if article is not None:
            articles.append(article)
    return _deduplicate(articles)


def _mercedes_api_articles(
    document: bytes,
    **common: object,
) -> tuple[NewsArticle, ...]:
    try:
        payload = json.loads(document.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return ()
    articles = []
    for item in payload["results"]:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id") or "").strip()
        image_uuid = str(item.get("header_image_uuid") or "").strip()
        article = _article(
            title=str(item.get("title") or ""),
            summary=str(
                item.get("fuel_label")
                or item.get("header_image_name")
                or item.get("title")
                or ""
            ),
            url=urljoin(
                str(common["source_url"]),
                f"/en/article/{identifier}",
            ),
            published=str(item.get("display_date") or item.get("creation_date") or ""),
            image_url=(
                "https://api.media.mercedes-benz.com/jsonapi/image/deliver/"
                f"{image_uuid}/4_3_800"
                if image_uuid
                else ""
            ),
            tags=tuple(
                value
                for key in ("location", "press_release_type")
                if (value := str(item.get(key) or "").strip())
            ),
            **common,
        )
        if identifier and article is not None:
            articles.append(article)
    return _deduplicate(articles)


def _article(
    *,
    title: str,
    summary: str,
    url: str,
    published: str,
    image_url: str,
    tags: tuple[str, ...],
    source: object,
    source_url: object,
    country: object,
    tracked_brands: object,
    tracked_vehicles: object,
    source_brand: object,
    official_brand_news: object,
) -> NewsArticle | None:
    clean_title = _clean(title)
    clean_summary = _clean(summary) or clean_title
    parsed_date = parse_publication_date(_clean(published))
    resolved_url = _https_url(url, base_url=str(source_url))
    if not clean_title or parsed_date is None or resolved_url is None:
        return None
    resolved_image = _https_url(image_url, base_url=resolved_url)
    brands, models = recognize_entities(
        f"{clean_title} {clean_summary} {' '.join(tags)} {resolved_url}",
        tracked_brands=tuple(tracked_brands),  # type: ignore[arg-type]
        tracked_vehicles=tuple(tracked_vehicles),  # type: ignore[arg-type]
        source_brand=str(source_brand) if source_brand else None,
    )
    source_text = str(source)
    return NewsArticle(
        article_id=hashlib.sha256(
            f"{source_text}\0{resolved_url}".encode()
        ).hexdigest()[:24],
        title=clean_title,
        summary=clean_summary,
        url=resolved_url,
        source=source_text,
        source_url=str(source_url),
        published_at=parsed_date,
        brands=brands,
        models=models,
        country=str(country),
        tags=tags,
        official_brand_news=bool(official_brand_news),
        image_url=resolved_image,
        image_source="provider_metadata" if resolved_image else None,
    )


def _https_url(value: str, *, base_url: str) -> str | None:
    if not value.strip():
        return None
    resolved = urljoin(base_url, html.unescape(value.strip()))
    parsed = urlparse(resolved)
    return resolved if parsed.scheme == "https" and parsed.netloc else None


def _clean(value: str) -> str:
    return _SPACE_PATTERN.sub(
        " ", html.unescape(_HTML_TAG_PATTERN.sub(" ", value))
    ).strip()


def _deduplicate(articles: list[NewsArticle]) -> tuple[NewsArticle, ...]:
    by_id = {article.article_id: article for article in articles}
    return tuple(
        sorted(by_id.values(), key=lambda item: item.published_at, reverse=True)
    )
