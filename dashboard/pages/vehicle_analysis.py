"""Vehicle Analysis page."""

from __future__ import annotations

from components.page_header import render_page_header
from components.placeholder import render_phase_placeholder


def render() -> None:
    """Render the Phase 17A Vehicle Analysis placeholder."""

    render_page_header(
        title="Vehicle Analysis",
        subtitle=(
            "A focused view for comparing canonical vehicles, variants, prices, "
            "and marketplace coverage."
        ),
    )
    render_phase_placeholder(
        page_name="Vehicle Analysis",
        description=(
            "Vehicle-level filters and comparisons are intentionally deferred "
            "until the read-only data connection is introduced."
        ),
        planned_items=(
            "Vehicle profile",
            "Peer comparison",
            "Listing distribution",
        ),
    )
