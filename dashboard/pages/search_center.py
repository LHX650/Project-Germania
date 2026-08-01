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
        subtitle=("通过只读 SQLite 连接查询可追溯的市场挂牌记录。"),
    )
    try:
        brands = list_listing_brands()
    except (FileNotFoundError, sqlite3.Error) as exc:
        st.error(f"只读数据库当前不可用：{exc}", icon="⚠️")
        return

    with st.form("listing_search_form"):
        first_row = st.columns((2, 1, 1, 1))
        query = first_row[0].text_input(
            "关键词",
            placeholder="车型、品牌、标题或 Listing ID",
        )
        brand_selection = first_row[1].selectbox("品牌", ("全部品牌", *brands))
        minimum_price = first_row[2].number_input(
            "最低价格(EUR)", min_value=0, value=0, step=1000
        )
        maximum_price = first_row[3].number_input(
            "最高价格(EUR)", min_value=0, value=0, step=1000
        )
        second_row = st.columns((1, 1, 3))
        active_only = second_row[0].checkbox("仅活跃挂牌", value=True)
        limit = second_row[1].selectbox("结果上限", (50, 100, 200, 500), index=2)
        submitted = st.form_submit_button(
            "查询挂牌",
            type="primary",
            width="stretch",
        )

    if not submitted:
        st.info("设置筛选条件后点击“查询挂牌”。所有查询均为参数化只读查询。")
        return

    try:
        results = search_listings(
            query=query,
            brand=None if brand_selection == "全部品牌" else brand_selection,
            minimum_price=minimum_price or None,
            maximum_price=maximum_price or None,
            active_only=active_only,
            limit=limit,
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.error(f"Listing 查询失败：{exc}", icon="⚠️")
        return

    st.metric("匹配结果", f"{len(results):,}")
    if not results:
        st.warning("当前筛选条件没有匹配的挂牌记录。")
        return

    rows = [_result_row(item) for item in results]
    st.dataframe(rows, hide_index=True, width="stretch", height=580)
    st.download_button(
        "下载查询结果 CSV",
        data=_to_csv(rows),
        file_name="project_germania_listing_search.csv",
        mime="text/csv",
        width="stretch",
    )
    st.caption(
        "数据来源：Project Germania SQLite 市场挂牌表。"
        "挂牌价不是成交价，查询结果不代表销量。"
    )


def _result_row(item: object) -> dict[str, object]:
    return {
        "Listing ID": item.external_listing_id,
        "品牌": item.brand_name,
        "车型": item.model_name,
        "标题": item.title,
        "挂牌价": item.current_price_amount,
        "货币": item.currency,
        "里程(km)": item.mileage_km,
        "燃料类型": item.fuel_type,
        "注册年份": item.registration_year,
        "城市": item.seller_city,
        "活跃": item.active,
        "最后采集时间": item.last_collected_at,
        "来源链接": item.listing_url,
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
