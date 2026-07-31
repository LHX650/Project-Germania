"""Data Quality page."""

from __future__ import annotations

from components.page_header import render_page_header
from components.placeholder import render_phase_placeholder


def render() -> None:
    """Render the Phase 17A Data Quality placeholder."""

    render_page_header(
        title="Data Quality",
        subtitle=(
            "A transparent control surface for completeness, consistency, "
            "validity, uniqueness, and timeliness indicators."
        ),
    )
    render_phase_placeholder(
        page_name="Data Quality",
        description=(
            "The page shell is ready, but quality scores and issue records remain "
            "disconnected from source data during this phase."
        ),
        planned_items=(
            "Quality summary",
            "Field completeness",
            "Issue review",
        ),
    )
