"""Read-only marketplace Listing Search Center."""

from __future__ import annotations

import csv
import sqlite3
from io import StringIO

import streamlit as st
from components.page_header import render_page_header
from services.database import list_listing_brands, search_listings


def render() -> None:
    """Render parameterized listing search over the read-only SQLite database."""

    render_page_header(
        title="Search Center",
        subtitle="Search traceable marketplace listings through read-only SQLite.",
    )
    try:
        brands = list_listing_brands()
    except (FileNotFoundError, sqlite3.Error) as exc:
        st.error(f"The read-only database is unavailable: {exc}", icon="⚠️")
        return

    with st.form("listing_search_form"):
        first_row = st.columns((2, 1, 1, 1))
        query = first_row[0].text_input(
            "Keyword",
            placeholder="Vehicle, brand, title, or Listing ID",
        )
        brand_selection = first_row[1].selectbox("Brand", ("All brands", *brands))
        minimum_price = first_row[2].number_input(
            "Minimum price (EUR)", min_value=0, value=0, step=1000
        )
        maximum_price = first_row[3].number_input(
            "Maximum price (EUR)", min_value=0, value=0, step=1000
        )
        second_row = st.columns((1, 1, 3))
        active_only = second_row[0].checkbox("Active listings only", value=True)
        limit = second_row[1].selectbox("Result limit", (50, 100, 200, 500), index=2)
        submitted = st.form_submit_button(
            "Search listings",
            type="primary",
            width="stretch",
        )

    if not submitted:
        st.info(
            "Set the filters, then select “Search listings.” All queries are "
            "parameterized and read-only."
        )
        return

    try:
        results = search_listings(
            query=query,
            brand=None if brand_selection == "All brands" else brand_selection,
            minimum_price=minimum_price or None,
            maximum_price=maximum_price or None,
            active_only=active_only,
            limit=limit,
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.error(f"Listing search failed: {exc}", icon="⚠️")
        return

    st.metric("Matching results", f"{len(results):,}")
    if not results:
        st.warning("No listings match the current filters.")
        return

    rows = [_result_row(item) for item in results]
    st.dataframe(rows, hide_index=True, width="stretch", height=580)
    st.download_button(
        "Download search results as CSV",
        data=_to_csv(rows),
        file_name="project_germania_listing_search.csv",
        mime="text/csv",
        width="stretch",
    )
    st.caption(
        "Source: Project Germania SQLite marketplace listings. Asking prices are "
        "not transaction prices, and search results do not represent sales."
    )


def _result_row(item: object) -> dict[str, object]:
    return {
        "Listing ID": item.external_listing_id,
        "Brand": item.brand_name,
        "Vehicle": item.model_name,
        "Title": item.title,
        "Asking price": item.current_price_amount,
        "Currency": item.currency,
        "Mileage (km)": item.mileage_km,
        "Fuel type": item.fuel_type,
        "Registration year": item.registration_year,
        "City": item.seller_city,
        "Active": item.active,
        "Last collected at": item.last_collected_at,
        "Source URL": item.listing_url,
    }


def _to_csv(rows: list[dict[str, object]]) -> bytes:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=tuple(rows[0]))
    writer.writeheader()
    writer.writerows(
        {key: _safe_csv_value(value) for key, value in row.items()} for row in rows
    )
    return buffer.getvalue().encode("utf-8-sig")


def _safe_csv_value(value: object) -> object:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value
