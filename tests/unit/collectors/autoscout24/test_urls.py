from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from germania.collectors.autoscout24 import SearchConfig, build_search_url


def test_build_search_url_for_german_brand_and_model() -> None:
    search_config = SearchConfig(brand="Volkswagen", model="Golf")

    url = build_search_url(search_config)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.autoscout24.de"
    assert parsed.path == "/lst/volkswagen/golf"
    assert query["atype"] == ["C"]
    assert query["cy"] == ["D"]
    assert query["ustate"] == ["N,U"]
    assert query["sort"] == ["standard"]
    assert query["desc"] == ["0"]


def test_build_search_url_with_optional_filters() -> None:
    search_config = SearchConfig(
        brand="BMW",
        model="iX1",
        postal_code="10115",
        radius_km=50,
        min_price_eur=30000,
        max_price_eur=55000,
        min_first_registration_year=2022,
        max_first_registration_year=2026,
        max_mileage_km=20000,
        fuel_type="electric",
        body_type="suv",
        seller_type="dealer",
        include_new=False,
        include_used=True,
        page=2,
        sort="price",
    )

    url = build_search_url(search_config)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.path == "/lst/bmw/ix1"
    assert query["zip"] == ["10115"]
    assert query["zipr"] == ["50"]
    assert query["pricefrom"] == ["30000"]
    assert query["priceto"] == ["55000"]
    assert query["fregfrom"] == ["2022"]
    assert query["fregto"] == ["2026"]
    assert query["kmto"] == ["20000"]
    assert query["fuel"] == ["electric"]
    assert query["body"] == ["suv"]
    assert query["seller"] == ["dealer"]
    assert query["ustate"] == ["U"]
    assert query["page"] == ["2"]
    assert query["sort"] == ["price"]


def test_build_search_url_supports_brand_only_search() -> None:
    url = build_search_url(SearchConfig(brand="Mercedes-Benz"))

    assert urlparse(url).path == "/lst/mercedes-benz"


def test_search_config_normalizes_whitespace() -> None:
    search_config = SearchConfig(
        brand="  Volkswagen   ",
        model="  Golf   Variant ",
        postal_code="10115",
        fuel_type="  electric ",
    )

    assert search_config.brand == "Volkswagen"
    assert search_config.model == "Golf Variant"
    assert search_config.fuel_type == "electric"
    assert (
        urlparse(build_search_url(search_config)).path == "/lst/volkswagen/golf-variant"
    )


def test_search_config_normalizes_matching_terms() -> None:
    search_config = SearchConfig(
        brand="BYD",
        model="Seal U",
        expected_model_name="  Seal U ",
        included_title_terms=(" Seal U ", "Sealion 6"),
        excluded_title_terms=(" Seal 6 ", "SEALION 7"),
    )

    assert search_config.expected_model_name == "Seal U"
    assert search_config.included_title_terms == ("Seal U", "Sealion 6")
    assert search_config.excluded_title_terms == ("Seal 6", "SEALION 7")


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"brand": ""}, "brand"),
        ({"brand": "Volkswagen", "country_code": "FR"}, "country_code=DE"),
        ({"brand": "Volkswagen", "postal_code": "1011"}, "postal_code"),
        ({"brand": "Volkswagen", "radius_km": 50}, "radius_km requires"),
        (
            {"brand": "Volkswagen", "min_price_eur": 30000, "max_price_eur": 10000},
            "price lower bound",
        ),
        (
            {
                "brand": "Volkswagen",
                "include_new": False,
                "include_used": False,
            },
            "At least one",
        ),
    ],
)
def test_search_config_rejects_invalid_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        SearchConfig(**kwargs)


def test_url_builder_rejects_non_german_autoscout24_base_url() -> None:
    with pytest.raises(ValueError, match="autoscout24.de"):
        build_search_url(
            SearchConfig(brand="Volkswagen"),
            base_url="https://www.autoscout24.fr",
        )
