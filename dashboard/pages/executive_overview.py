"""Executive Overview page."""

from __future__ import annotations

from components.page_header import render_page_header
from components.placeholder import render_phase_placeholder


def render() -> None:
    """Render the Phase 17A Executive Overview placeholder."""

    render_page_header(
        title="Executive Overview",
        subtitle=(
            "A leadership-ready entry point for German automotive market signals, "
            "coverage, and platform status."
        ),
    )
    render_phase_placeholder(
        page_name="Executive Overview",
        description=(
            "This foundation reserves space for concise market KPIs and decision "
            "support without displaying unverified or simulated figures."
        ),
        planned_items=(
            "Market snapshot",
            "Coverage status",
            "Priority signals",
        ),
    )
