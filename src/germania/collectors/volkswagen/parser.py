"""Local HTML parser for Volkswagen Germany official prices."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

from germania.collectors.volkswagen.config import VOLKSWAGEN_DE_BASE_URL
from germania.collectors.volkswagen.models import OfficialPriceRecord

logger = logging.getLogger(__name__)

_FIELD_ATTRIBUTE = "data-field"
_PRICE_CARD_ATTRIBUTE = "data-price-card"
_PRICE_TYPE_ATTRIBUTE = "data-price-type"
_ACCEPTED_PRICE_TYPES = frozenset(
    {
        "official_starting_price",
        "official_base_price",
    }
)
_NUMBER_PATTERN = re.compile(r"\d[\d\s.,]*")
_WHITESPACE_PATTERN = re.compile(r"\s+")


class VolkswagenOfficialPriceParser:
    """Parse local Volkswagen Germany HTML into official price records."""

    def parse_price_page(
        self,
        html: str,
        *,
        source_url: str | None = None,
        collected_at: datetime | None = None,
    ) -> list[OfficialPriceRecord]:
        """Parse official price records from a local HTML page string."""

        parsed_at = _resolve_collected_at(collected_at)
        root = _parse_html(html)
        return [
            _record_from_node(node, source_url=source_url, collected_at=parsed_at)
            for node in _find_official_price_nodes(root)
        ]


def parse_official_prices(
    html: str,
    *,
    source_url: str | None = None,
    collected_at: datetime | None = None,
) -> list[OfficialPriceRecord]:
    """Parse official Volkswagen price records from a local HTML page string."""

    return VolkswagenOfficialPriceParser().parse_price_page(
        html,
        source_url=source_url,
        collected_at=collected_at,
    )


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def text_content(self) -> str:
        """Return normalized text for this node and all descendants."""

        text = "".join(self.text_parts)
        child_text = "".join(child.text_content() for child in self.children)
        return _clean_text(f"{text} {child_text}")

    def descendants(self) -> list[_Node]:
        """Return all descendant nodes in document order."""

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
            tag.casefold(),
            {key.casefold(): value or "" for key, value in attrs},
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
            "Volkswagen HTML parsing recovered from malformed input: %s",
            exc,
        )
    return parser.root


def _find_official_price_nodes(root: _Node) -> list[_Node]:
    return [
        node
        for node in root.descendants()
        if node.attrs.get(_PRICE_CARD_ATTRIBUTE) is not None
        and _price_type(node) in _ACCEPTED_PRICE_TYPES
    ]


def _record_from_node(
    node: _Node,
    *,
    source_url: str | None,
    collected_at: datetime,
) -> OfficialPriceRecord:
    raw_price_text = _field_text(node, "price")
    parsed_price = _parse_price(raw_price_text)
    parsed_currency = _parse_currency(raw_price_text)
    valid_date = _parse_date(_field_text(node, "valid_date"))
    observed_at = _parse_datetime(_field_text(node, "observed_at"))

    return OfficialPriceRecord(
        source_url=source_url or _node_source_url(node),
        raw_brand_name=_field_text(node, "brand"),
        raw_model_name=_field_text(node, "model"),
        raw_variant_name=_field_text(node, "variant"),
        canonical_brand_name=_field_text(node, "canonical_brand")
        or _field_text(node, "brand"),
        canonical_model_name=_field_text(node, "canonical_model")
        or _field_text(node, "model"),
        price_type=_price_type(node),
        original_price=parsed_price,
        original_currency=parsed_currency,
        price_eur=parsed_price if parsed_currency == "EUR" else None,
        raw_price_text=raw_price_text,
        observed_at=observed_at,
        valid_date=valid_date,
        collected_at=collected_at,
        price_includes_vat=_parse_bool(_field_text(node, "price_includes_vat")),
    )


def _price_type(node: _Node) -> str:
    price_type = _clean_text(node.attrs.get(_PRICE_TYPE_ATTRIBUTE))
    return price_type or "unknown"


def _node_source_url(node: _Node) -> str | None:
    source_url = _clean_text(node.attrs.get("data-source-url"))
    if source_url:
        return urljoin(VOLKSWAGEN_DE_BASE_URL, source_url)
    link_node = _find_first_descendant(
        node,
        lambda candidate: candidate.tag == "a" and bool(candidate.attrs.get("href")),
    )
    if link_node is None:
        return None
    href = _clean_text(link_node.attrs.get("href"))
    return urljoin(VOLKSWAGEN_DE_BASE_URL, href) if href else None


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
    if "\u20ac" in value or "eur" in normalized:
        return "EUR"
    return None


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.casefold()
    if normalized in {"true", "yes", "1", "ja"}:
        return True
    if normalized in {"false", "no", "0", "nein"}:
        return False
    return None


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
