"""Search Center page."""

from __future__ import annotations

from components.page_header import render_page_header
from components.placeholder import render_phase_placeholder


def render() -> None:
    """Render the Phase 17A Search Center placeholder."""

    render_page_header(
        title="Search Center",
        subtitle=(
            "A future controlled search workspace for vehicles, listings, sources, "
            "and traceable records."
        ),
    )
    render_phase_placeholder(
        page_name="Search Center",
        description=(
            "Search inputs and result tables will be introduced only after safe, "
            "read-only data services are connected."
        ),
        planned_items=(
            "Vehicle lookup",
            "Listing search",
            "Source traceability",
        ),
    )
