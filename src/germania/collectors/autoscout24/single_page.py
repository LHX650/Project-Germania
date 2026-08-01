"""Single-page AutoScout24 collection, parsing, and import workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from germania.collectors.autoscout24.collector import AutoScout24Collector
from germania.collectors.autoscout24.config import SearchConfig
from germania.collectors.autoscout24.import_service import (
    AutoScout24ImportResult,
    AutoScout24ListingImportService,
)
from germania.collectors.autoscout24.matching import (
    VehicleMatchSummary,
    evaluate_vehicle_matches,
)
from germania.collectors.autoscout24.parser import AutoScout24ListingParser
from germania.collectors.exceptions import CollectorError

SinglePageMode = Literal["dry_run", "import"]


@dataclass(frozen=True)
class AutoScout24SinglePageResult:
    """Traceable result for one single-page collection workflow."""

    mode: SinglePageMode
    source_url: str
    raw_html_path: Path
    content_sha256: str
    parsed: int
    matching: VehicleMatchSummary
    import_result: AutoScout24ImportResult


class AutoScout24SinglePagePipeline:
    """Run Playwright to HTML to parser to repository for exactly one page."""

    def __init__(
        self,
        collector: AutoScout24Collector,
        session: Session,
        *,
        parser: AutoScout24ListingParser | None = None,
    ) -> None:
        self.collector = collector
        self.session = session
        self.parser = parser or AutoScout24ListingParser()

    def run(
        self,
        search_config: SearchConfig,
        *,
        raw_html_path: Path | str,
        mode: SinglePageMode = "dry_run",
    ) -> AutoScout24SinglePageResult:
        """Collect, preserve, parse, and optionally import one listing page."""

        if mode not in {"dry_run", "import"}:
            raise ValueError("mode must be either 'dry_run' or 'import'")

        try:
            loaded_page = self.collector.load_listing_page(search_config)
            saved_path = _save_raw_html(raw_html_path, loaded_page.html)
            records = self.parser.parse_marketplace_listing_page(
                loaded_page.html,
                collected_at=loaded_page.metadata.collected_at,
            )
            match_evaluation = evaluate_vehicle_matches(
                records,
                expected_model_name=(
                    search_config.expected_model_name or search_config.model
                ),
                include_keywords=search_config.included_title_terms,
                exclude_keywords=search_config.excluded_title_terms,
            )
            records = list(match_evaluation.records)
            service = AutoScout24ListingImportService(
                self.session,
                parser=self.parser,
            )
            if mode == "dry_run":
                import_result = service.dry_run_records(records)
            else:
                import_result = service.import_records(records)

            content_sha256 = loaded_page.metadata.content_sha256
            if content_sha256 is None:
                raise CollectorError("Collected HTML is missing its SHA-256 hash")
            return AutoScout24SinglePageResult(
                mode=mode,
                source_url=loaded_page.url,
                raw_html_path=saved_path,
                content_sha256=content_sha256,
                parsed=len(records),
                matching=match_evaluation.summary,
                import_result=import_result,
            )
        finally:
            self.collector.close()


def _save_raw_html(path: Path | str, html: str) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x", encoding="utf-8", newline="") as output_file:
            output_file.write(html)
    except FileExistsError as exc:
        raise CollectorError(
            f"Raw AutoScout24 HTML already exists and will not be overwritten: "
            f"{output_path}"
        ) from exc
    return output_path
