"""HTML parser for AutoScout24 Germany listing cards."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse

from germania.collectors.autoscout24.config import (
    AUTOSCOUT24_DE_BASE_URL,
    AUTOSCOUT24_DE_SOURCE_ID,
)
from germania.collectors.autoscout24.models import ListingRecord
from germania.collectors.marketplace import MarketplaceListingRecord

logger = logging.getLogger(__name__)

_LISTING_TEST_IDS = frozenset({"list-item", "listing-card", "listing-item"})
_LISTING_CLASS_NAMES = frozenset({"listing-card", "listing-item"})
_FIELD_ATTRIBUTE = "data-field"
_LISTING_ID_ATTRIBUTES = (
    "data-listing-id",
    "data-source-listing-id",
    "data-guid",
)
_FIELD_TEST_IDS = {
    "registration": "VehicleDetails-calendar",
    "mileage": "VehicleDetails-mileage_odometer",
    "fuel_type": "VehicleDetails-gas_pump",
    "power": "VehicleDetails-speedometer",
    "location": "dealer-address",
    "seller_name": "dealer-company-name",
}
_FIELD_CLASS_PREFIXES = {
    "title": "ListItemTitle_heading__",
    "variant": "ListItemTitle_subtitle__",
}
_FIELD_NODE_ATTRIBUTES = {
    "brand": "data-make",
    "model": "data-model",
    "registration": "data-first-registration",
    "mileage": "data-mileage",
    "seller_type": "data-seller-type",
}
_NUMBER_PATTERN = re.compile(r"\d[\d\s.,]*")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_REGISTRATION_YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_POWER_KW_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*kW\b", re.IGNORECASE)
_POWER_PS_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*PS\b", re.IGNORECASE)
_POSTCODE_CITY_PATTERN = re.compile(
    r"(?:\b[A-Z]{2}\s*[- ]\s*)?(?P<postcode>\d{5})\s+(?P<city>.+)$",
    re.IGNORECASE,
)
_EXCLUDED_PRICE_TYPES = frozenset(
    {"advertisement", "financing", "leasing", "monthly", "old", "previous"}
)
_EXCLUDED_PRICE_TERMS = (
    " / monat",
    "/monat",
    "monatlich",
    "finanzierung",
    "leasing",
    "monatsrate",
    "rate ab",
    "werbung",
    "ehemal",
    "vorher",
    "altpreis",
)
_FUEL_TYPE_MAP = {
    "benzin": "petrol",
    "diesel": "diesel",
    "elektro": "electric",
    "hybrid": "hybrid",
}
_TRANSMISSION_MAP = {
    "automatik": "automatic",
    "schaltgetriebe": "manual",
    "manuell": "manual",
}
_SELLER_TYPE_MAP = {
    "d": "dealer",
    "handler": "dealer",
    "haendler": "dealer",
    "dealer": "dealer",
    "privat": "private",
    "private": "private",
    "p": "private",
    "hersteller": "manufacturer",
    "manufacturer": "manufacturer",
}
_CONDITION_MAP = {
    "gebraucht": "used",
    "used": "used",
    "neu": "new",
    "new": "new",
    "vorfuhrfahrzeug": "demonstrator",
    "demonstrator": "demonstrator",
}
_ALLOWED_AUTOSCOUT24_HOSTS = frozenset({"autoscout24.de", "www.autoscout24.de"})


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
        listing_urls = _extract_embedded_listing_urls(root)
        if listing_nodes:
            return _record_from_node(listing_nodes[0], parsed_at, listing_urls)
        if _has_listing_signal(root):
            return _record_from_node(root, parsed_at, listing_urls)
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
        listing_urls = _extract_embedded_listing_urls(root)
        records = [
            _record_from_node(node, parsed_at, listing_urls)
            for node in _find_listing_nodes(root)
        ]
        _warn_for_missing_live_fields(records)
        return records

    def parse_marketplace_listing_page(
        self,
        html: str,
        *,
        collected_at: datetime | None = None,
    ) -> list[MarketplaceListingRecord]:
        """Parse listing cards into the shared marketplace repository contract."""

        return [
            _to_marketplace_record(record)
            for record in self.parse_listing_page(html, collected_at=collected_at)
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


def parse_marketplace_listing_page(
    html: str,
    *,
    collected_at: datetime | None = None,
) -> list[MarketplaceListingRecord]:
    """Parse AutoScout24 cards into normalized marketplace listing records."""

    return AutoScout24ListingParser().parse_marketplace_listing_page(
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
        text = " ".join(self.text_parts)
        child_text = " ".join(child.text_content() for child in self.children)
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


def _record_from_node(
    node: _Node,
    collected_at: datetime,
    listing_urls: dict[str, str] | None = None,
) -> ListingRecord:
    price_text = _vehicle_price_text(node)
    listing_id = _extract_listing_id(node, None)
    embedded_url = (listing_urls or {}).get(listing_id or "")
    url = _extract_url(node, embedded_url=embedded_url)
    return ListingRecord(
        source_id=AUTOSCOUT24_DE_SOURCE_ID,
        listing_id=listing_id or _extract_listing_id(node, url),
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
        title=_field_text(node, "title"),
        seller_type=_map_seller_type(_field_text(node, "seller_type")),
        seller_name=_field_text(node, "seller_name"),
        vehicle_condition=_map_vehicle_condition(
            _field_text(node, "vehicle_condition")
        ),
        body_type=_field_text(node, "body_type"),
        color=_field_text(node, "color"),
    )


def _field_text(node: _Node, field_name: str) -> str | None:
    field_node = _find_first_descendant(
        node,
        lambda candidate: candidate.attrs.get(_FIELD_ATTRIBUTE) == field_name,
    )
    if field_node is not None:
        return _clean_text(field_node.text_content()) or None

    test_id = _FIELD_TEST_IDS.get(field_name)
    if test_id is not None:
        field_node = _find_first_descendant(
            node,
            lambda candidate: candidate.attrs.get("data-testid") == test_id,
        )
        if field_node is not None:
            return _clean_text(field_node.text_content()) or None

    class_prefix = _FIELD_CLASS_PREFIXES.get(field_name)
    if class_prefix is not None:
        field_node = _find_first_descendant(
            node,
            lambda candidate: any(
                class_name.startswith(class_prefix)
                for class_name in candidate.attrs.get("class", "").split()
            ),
        )
        if field_node is not None:
            return _clean_text(field_node.text_content()) or None

    attribute = _FIELD_NODE_ATTRIBUTES.get(field_name)
    if attribute is None:
        return None
    value = _clean_text(node.attrs.get(attribute))
    return _humanize_taxonomy_value(value) if value else None


def _vehicle_price_text(node: _Node) -> str | None:
    for candidate in node.descendants():
        if candidate.attrs.get(_FIELD_ATTRIBUTE) != "price":
            continue
        price_type = candidate.attrs.get("data-price-type", "").casefold()
        text = _clean_text(candidate.text_content())
        if price_type in _EXCLUDED_PRICE_TYPES or _is_excluded_price_text(text):
            continue
        if _parse_currency(text) == "EUR" and _parse_price(text) is not None:
            return text
    regular_price = _find_first_descendant(
        node,
        lambda candidate: candidate.attrs.get("data-testid") == "regular-price",
    )
    if regular_price is not None:
        text = _clean_text(regular_price.text_content())
        if _parse_currency(text) == "EUR" and _parse_price(text) is not None:
            return text
    raw_price = _clean_text(node.attrs.get("data-price"))
    if _parse_price(raw_price) is not None:
        return f"€ {raw_price}"
    return None


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
    if len(path_parts) < 2 or path_parts[-1].casefold() == "angebote":
        return None
    return path_parts[-1]


def _extract_url(node: _Node, *, embedded_url: str | None = None) -> str | None:
    url_node = _find_first_descendant(
        node,
        lambda candidate: candidate.tag == "a"
        and (
            candidate.attrs.get(_FIELD_ATTRIBUTE) == "url"
            or "/angebote/" in candidate.attrs.get("href", "")
        ),
    )
    href = _clean_text(url_node.attrs.get("href")) if url_node is not None else ""
    if not href:
        href = _clean_text(embedded_url)
    if not href:
        return None
    absolute_url = urljoin(AUTOSCOUT24_DE_BASE_URL, href)
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.casefold() not in (
        _ALLOWED_AUTOSCOUT24_HOSTS
    ):
        return None
    return urlunparse(("https", parsed.netloc.casefold(), parsed.path, "", "", ""))


def _extract_embedded_listing_urls(root: _Node) -> dict[str, str]:
    listing_urls: dict[str, str] = {}
    for node in root.descendants():
        if node.tag != "script" or node.attrs.get("id") != "__NEXT_DATA__":
            continue
        raw_json = "".join(node.text_parts).strip()
        if not raw_json:
            continue
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.warning("Could not parse AutoScout24 __NEXT_DATA__: %s", exc)
            continue
        _collect_listing_urls(payload, listing_urls)
    return listing_urls


def _collect_listing_urls(value: object, listing_urls: dict[str, str]) -> None:
    if isinstance(value, dict):
        listing_id = value.get("id")
        url = value.get("url")
        if isinstance(listing_id, str) and isinstance(url, str) and "/angebote/" in url:
            normalized_url = _normalize_listing_url(url)
            if normalized_url is not None:
                listing_urls[listing_id] = normalized_url
        for nested in value.values():
            _collect_listing_urls(nested, listing_urls)
    elif isinstance(value, list):
        for nested in value:
            _collect_listing_urls(nested, listing_urls)


def _normalize_listing_url(value: str) -> str | None:
    absolute_url = urljoin(AUTOSCOUT24_DE_BASE_URL, value)
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.casefold() not in _ALLOWED_AUTOSCOUT24_HOSTS:
        return None
    return urlunparse(("https", parsed.netloc.casefold(), parsed.path, "", "", ""))


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


def _to_marketplace_record(record: ListingRecord) -> MarketplaceListingRecord:
    seller_postcode, seller_city = _parse_location(record.location)
    return MarketplaceListingRecord(
        source_id=record.source_id,
        external_listing_id=record.listing_id or "",
        collected_at=record.collected_at,
        listing_url=record.url,
        brand_name=record.brand,
        model_name=record.model,
        variant_name=record.variant,
        title=record.title,
        price_amount=record.price,
        currency=record.currency or "EUR",
        registration_year=_parse_registration_year(record.registration),
        mileage_km=record.mileage,
        fuel_type=_map_optional_text(record.fuel_type, _FUEL_TYPE_MAP),
        transmission=_map_optional_text(record.transmission, _TRANSMISSION_MAP),
        power_kw=_parse_power_kw(record.power),
        seller_type=record.seller_type,
        seller_name=record.seller_name,
        seller_postcode=seller_postcode,
        seller_city=seller_city,
        vehicle_condition=record.vehicle_condition,
        body_type=record.body_type,
        color=record.color,
    )


def _parse_registration_year(value: str | None) -> int | None:
    if value is None:
        return None
    match = _REGISTRATION_YEAR_PATTERN.search(value)
    if match is None:
        return None
    year = int(match.group(0))
    return year if 1886 <= year <= 2100 else None


def _parse_power_kw(value: str | None) -> Decimal | None:
    if value is None:
        return None
    kw_match = _POWER_KW_PATTERN.search(value)
    if kw_match is not None:
        return _decimal_from_number(kw_match.group(1))
    ps_match = _POWER_PS_PATTERN.search(value)
    if ps_match is None:
        return None
    power_ps = _decimal_from_number(ps_match.group(1))
    if power_ps is None:
        return None
    return (power_ps * Decimal("0.73549875")).quantize(Decimal("0.01"))


def _decimal_from_number(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def _parse_location(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    match = _POSTCODE_CITY_PATTERN.search(value)
    if match is None:
        return None, None
    return match.group("postcode"), _clean_text(match.group("city")) or None


def _map_optional_text(value: str | None, mapping: dict[str, str]) -> str | None:
    if value is None:
        return None
    normalized = _ascii_key(value)
    return mapping.get(normalized, _clean_text(value).casefold())


def _map_seller_type(value: str | None) -> str | None:
    if value is None:
        return None
    return _SELLER_TYPE_MAP.get(_ascii_key(value), "unknown")


def _map_vehicle_condition(value: str | None) -> str | None:
    if value is None:
        return None
    return _CONDITION_MAP.get(_ascii_key(value), "unknown")


def _ascii_key(value: str) -> str:
    return (
        value.casefold()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
        .strip()
    )


def _is_excluded_price_text(value: str) -> bool:
    normalized = value.casefold()
    return any(term in normalized for term in _EXCLUDED_PRICE_TERMS)


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


def _humanize_taxonomy_value(value: str) -> str:
    return " ".join(part[:1].upper() + part[1:] for part in value.split())


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
        "title",
        "seller_type",
        "seller_name",
        "vehicle_condition",
        "body_type",
        "color",
    )


def _warn_for_missing_live_fields(records: list[ListingRecord]) -> None:
    if not records:
        logger.warning("AutoScout24 parser found no listing cards in the loaded HTML")
        return

    required_fields = {
        "external_listing_id": "listing_id",
        "brand": "brand",
        "model": "model",
        "variant": "variant",
        "price": "price",
        "mileage": "mileage",
        "registration": "registration",
        "location": "location",
        "detail_url": "url",
    }
    for output_name, attribute_name in required_fields.items():
        missing = sum(
            getattr(record, attribute_name) in (None, "") for record in records
        )
        if missing:
            logger.warning(
                "AutoScout24 parser missing field=%s records=%s total=%s",
                output_name,
                missing,
                len(records),
            )
