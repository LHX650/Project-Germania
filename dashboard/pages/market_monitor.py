"""Market Monitor page."""

from __future__ import annotations

from components.page_header import render_page_header
from components.placeholder import render_phase_placeholder


def render() -> None:
    """Render the Phase 17A Market Monitor placeholder."""

    render_page_header(
        title="Market Monitor",
        subtitle=(
            "A future monitoring surface for bounded collection-window changes "
            "and clearly qualified marketplace signals."
        ),
    )
    render_phase_placeholder(
        page_name="Market Monitor",
        description=(
            "No monitoring logic is implemented in Phase 17A, and inferred listing "
            "changes are not presented as confirmed sales or permanent removals."
        ),
        planned_items=(
            "New listings",
            "Price movements",
            "Collection-window changes",
        ),
    )
