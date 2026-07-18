"""HTML parser for AutoScout24 Germany listing cards."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from germania.collectors.autoscout24.config import (
    AUTOSCOUT24_DE_BASE_URL,
    AUTOSCOUT24_DE_SOURCE_ID,
)
from germania.collectors.autoscout24.models import ListingRecord

logger = logging.getLogger(__name__)

_LISTING_TEST_IDS = frozenset({"listing-card", "listing-item"})
_LISTING_CLASS_NAMES = frozenset({"listing-card", "listing-item"})
_FIELD_ATTRIBUTE = "data-field"
_LISTING_ID_ATTRIBUTES = ("data-listing-id", "data-source-listing-id", "data-id")
_NUMBER_PATTERN = re.compile(r"\d[\d\s.,]*")
_WHITESPACE_PATTERN = re.compile(r"\s+")


class AutoScout24ListingParser:
    """Parse local AutoScout24 listing HTML into ListingRecord objects."""

    def parse_listing(
        self,
        html: str,
        *,
        collected_at: datetime | None = None,
    ) -> ListingRecord | None:
        """Parse a single listing HTML fragment."""
        parsed_at = _resolve_collected_at(collected_at)
        root = _parse_html(html)
        listing_nodes = _find_listing_nodes(root)
        if listing_nodes:
            return _record_from_node(listing_nodes[0], parsed_at)
        if _has_listing_signal(root):
            return _record_from_node(root, parsed_at)
        return None

    def parse_listing_page(
        self,
        html: str,
        *,
        collected_at: datetime | None = None,
    ) -> list[ListingRecord]:
        """Parse all listing cards found in a listing page HTML string."""
        parsed_at = _resolve_collected_at(collected_at)
        root = _parse_html(html)
        return [
            _record_from_node(node, parsed_at) for node in _find_listing_nodes(root)
        ]


def parse_listing(
    html: str,
    *,
    collected_at: datetime | None = None,
) -> ListingRecord | None:
    """Parse a single listing HTML fragment."""
    return AutoScout24ListingParser().parse_listing(html, collected_at=collected_at)


def parse_listing_page(
    html: str,
    *,
    collected_at: datetime | None = None,
) -> list[ListingRecord]:
    """Parse all listing cards in a listing page HTML string."""
    return AutoScout24ListingParser().parse_listing_page(
        html,
        collected_at=collected_at,
    )


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def text_content(self) -> str:
        text = "".join(self.text_parts)
        child_text = "".join(child.text_content() for child in self.children)
        return _clean_text(f"{text} {child_text}")

    def descendants(self) -> list[_Node]:
        nodes: list[_Node] = []
        for child in self.children:
            nodes.append(child)
            nodes.extend(child.descendants())
        return nodes


class _DOMParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self._stack = [self.root]

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        node = _Node(
            tag.casefold(), {key.casefold(): value or "" for key, value in attrs}
        )
        self._stack[-1].children.append(node)
        if tag.casefold() not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == normalized_tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].text_parts.append(data)


def _parse_html(html: str) -> _Node:
    parser = _DOMParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception as exc:
        logger.warning(
            "AutoScout24 HTML parsing recovered from malformed input: %s", exc
        )
    return parser.root


def _find_listing_nodes(root: _Node) -> list[_Node]:
    return [node for node in root.descendants() if _is_listing_node(node)]


def _is_listing_node(node: _Node) -> bool:
    if any(node.attrs.get(attribute) for attribute in _LISTING_ID_ATTRIBUTES):
        return True
    if node.attrs.get("data-testid") in _LISTING_TEST_IDS:
        return True
    class_names = set(node.attrs.get("class", "").split())
    return bool(_LISTING_CLASS_NAMES.intersection(class_names))


def _has_listing_signal(node: _Node) -> bool:
    if _is_listing_node(node):
        return True
    return any(
        _field_text(node, field_name) is not None for field_name in _field_names()
    )


def _record_from_node(node: _Node, collected_at: datetime) -> ListingRecord:
    price_text = _field_text(node, "price")
    url = _extract_url(node)
    return ListingRecord(
        source_id=AUTOSCOUT24_DE_SOURCE_ID,
        listing_id=_extract_listing_id(node, url),
        brand=_field_text(node, "brand"),
        model=_field_text(node, "model"),
        variant=_field_text(node, "variant"),
        price=_parse_price(price_text),
        currency=_parse_currency(price_text),
        registration=_field_text(node, "registration"),
        mileage=_parse_integer(_field_text(node, "mileage")),
        fuel_type=_field_text(node, "fuel_type"),
        transmission=_field_text(node, "transmission"),
        power=_field_text(node, "power"),
        location=_field_text(node, "location"),
        url=url,
        collected_at=collected_at,
    )


def _field_text(node: _Node, field_name: str) -> str | None:
    field_node = _find_first_descendant(
        node,
        lambda candidate: candidate.attrs.get(_FIELD_ATTRIBUTE) == field_name,
    )
    if field_node is None:
        return None
    return _clean_text(field_node.text_content()) or None


def _find_first_descendant(node: _Node, predicate: object) -> _Node | None:
    for candidate in node.descendants():
        if predicate(candidate):
            return candidate
    return None


def _extract_listing_id(node: _Node, url: str | None) -> str | None:
    for attribute in _LISTING_ID_ATTRIBUTES:
        value = _clean_text(node.attrs.get(attribute))
        if value:
            return value
    if url is None:
        return None
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if not path_parts:
        return None
    return path_parts[-1]


def _extract_url(node: _Node) -> str | None:
    url_node = _find_first_descendant(
        node,
        lambda candidate: candidate.tag == "a"
        and (
            candidate.attrs.get(_FIELD_ATTRIBUTE) == "url"
            or bool(candidate.attrs.get("href"))
        ),
    )
    if url_node is None:
        return None
    href = _clean_text(url_node.attrs.get("href"))
    if not href:
        return None
    return urljoin(AUTOSCOUT24_DE_BASE_URL, href)


def _parse_price(value: str | None) -> Decimal | None:
    if value is None:
        return None
    match = _NUMBER_PATTERN.search(value)
    if match is None:
        return None
    normalized = _normalize_decimal_text(match.group(0))
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _parse_currency(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.casefold()
    if "€" in value or "eur" in normalized:
        return "EUR"
    return None


def _parse_integer(value: str | None) -> int | None:
    if value is None:
        return None
    match = _NUMBER_PATTERN.search(value)
    if match is None:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    return int(digits) if digits else None


def _normalize_decimal_text(value: str) -> str:
    normalized = value.replace(" ", "").strip(".,")
    if "," in normalized and "." in normalized:
        return normalized.replace(".", "").replace(",", ".").strip(".")
    if "," in normalized:
        before, _, after = normalized.partition(",")
        if len(after) == 2:
            return f"{before}.{after}"
        return normalized.replace(",", "")
    if normalized.count(".") == 1:
        before, _, after = normalized.partition(".")
        if len(after) == 2:
            return f"{before}.{after}"
    return normalized.replace(".", "")


def _clean_text(value: str | None) -> str:
    return _WHITESPACE_PATTERN.sub(" ", unescape(value or "")).strip()


def _resolve_collected_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _field_names() -> tuple[str, ...]:
    return (
        "brand",
        "model",
        "variant",
        "price",
        "registration",
        "mileage",
        "fuel_type",
        "transmission",
        "power",
        "location",
    )
