"""Search configuration for German AutoScout24 listing pages."""

from __future__ import annotations

import re
from dataclasses import dataclass

AUTOSCOUT24_DE_SOURCE_ID = "autoscout24_de"
AUTOSCOUT24_DE_BASE_URL = "https://www.autoscout24.de"
AUTOSCOUT24_DE_COUNTRY_CODE = "DE"
DEFAULT_SORT = "standard"

ALLOWED_SORT_VALUES = frozenset(
    {
        "standard",
        "price",
        "mileage",
        "age",
    }
)
_POSTAL_CODE_PATTERN = re.compile(r"^\d{5}$")


@dataclass(frozen=True)
class SearchConfig:
    """Validated search parameters for German AutoScout24 search URLs."""

    brand: str
    model: str | None = None
    country_code: str = AUTOSCOUT24_DE_COUNTRY_CODE
    postal_code: str | None = None
    radius_km: int | None = None
    min_price_eur: int | None = None
    max_price_eur: int | None = None
    min_first_registration_year: int | None = None
    max_first_registration_year: int | None = None
    max_mileage_km: int | None = None
    fuel_type: str | None = None
    body_type: str | None = None
    seller_type: str | None = None
    include_new: bool = True
    include_used: bool = True
    page: int = 1
    sort: str = DEFAULT_SORT
    search_url: str | None = None
    excluded_title_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        brand = _required_text(self.brand, "brand")
        model = _optional_text(self.model, "model")
        country_code = _required_text(self.country_code, "country_code").upper()

        if country_code != AUTOSCOUT24_DE_COUNTRY_CODE:
            raise ValueError("AutoScout24 collector only supports country_code=DE")
        if not self.include_new and not self.include_used:
            raise ValueError("At least one of include_new or include_used must be true")
        if self.sort not in ALLOWED_SORT_VALUES:
            allowed = ", ".join(sorted(ALLOWED_SORT_VALUES))
            raise ValueError(f"sort must be one of: {allowed}")

        postal_code = _optional_text(self.postal_code, "postal_code")
        if postal_code is not None and not _POSTAL_CODE_PATTERN.fullmatch(postal_code):
            raise ValueError("postal_code must contain exactly five digits")
        if self.radius_km is not None and postal_code is None:
            raise ValueError("radius_km requires postal_code")

        _validate_optional_positive_int(self.radius_km, "radius_km")
        _validate_optional_non_negative_int(self.min_price_eur, "min_price_eur")
        _validate_optional_non_negative_int(self.max_price_eur, "max_price_eur")
        _validate_optional_positive_int(self.max_mileage_km, "max_mileage_km")
        _validate_optional_year(
            self.min_first_registration_year,
            "min_first_registration_year",
        )
        _validate_optional_year(
            self.max_first_registration_year,
            "max_first_registration_year",
        )
        _validate_range(self.min_price_eur, self.max_price_eur, "price")
        _validate_range(
            self.min_first_registration_year,
            self.max_first_registration_year,
            "first_registration_year",
        )
        _validate_positive_int(self.page, "page")

        object.__setattr__(self, "brand", brand)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "country_code", country_code)
        object.__setattr__(self, "postal_code", postal_code)
        object.__setattr__(
            self, "fuel_type", _optional_text(self.fuel_type, "fuel_type")
        )
        object.__setattr__(
            self, "body_type", _optional_text(self.body_type, "body_type")
        )
        object.__setattr__(
            self,
            "seller_type",
            _optional_text(self.seller_type, "seller_type"),
        )
        object.__setattr__(
            self,
            "search_url",
            _optional_text(self.search_url, "search_url"),
        )
        object.__setattr__(
            self,
            "excluded_title_terms",
            _validated_title_terms(self.excluded_title_terms),
        )

    @property
    def vehicle_state_query_value(self) -> str:
        """Return AutoScout24 state query value for new and used listings."""
        if self.include_new and self.include_used:
            return "N,U"
        if self.include_new:
            return "N"
        return "U"


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return " ".join(value.strip().split())


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be null or non-empty text")
    return " ".join(value.strip().split())


def _validate_optional_positive_int(value: object, field: str) -> None:
    if value is not None:
        _validate_positive_int(value, field)


def _validate_optional_non_negative_int(value: object, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")


def _validate_positive_int(value: object, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")


def _validate_optional_year(value: object, field: str) -> None:
    if value is None:
        return
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1900 <= value <= 2100
    ):
        raise ValueError(f"{field} must be an integer year between 1900 and 2100")


def _validate_range(
    lower_value: int | None,
    upper_value: int | None,
    label: str,
) -> None:
    if (
        lower_value is not None
        and upper_value is not None
        and lower_value > upper_value
    ):
        raise ValueError(
            f"{label} lower bound must be less than or equal to upper bound"
        )


def _validated_title_terms(values: object) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not all(
        isinstance(value, str) for value in values
    ):
        raise ValueError("excluded_title_terms must be a tuple of non-empty strings")
    normalized = tuple(" ".join(value.strip().split()) for value in values)
    if any(not value for value in normalized):
        raise ValueError("excluded_title_terms must not contain empty strings")
    if len({value.casefold() for value in normalized}) != len(normalized):
        raise ValueError("excluded_title_terms must not contain duplicates")
    return normalized
