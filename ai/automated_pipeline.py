"""Opt-in collection -> Analytics -> AI wrapper without production-chain edits."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ai.pipeline import (
    DEFAULT_AI_OUTPUT,
    DEFAULT_ANALYTICS_INPUT,
    AIStageResult,
    run_ai_report_stage,
)

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAILY_MONITOR = PROJECT_ROOT / "scripts" / "daily_market_monitor.py"


@dataclass(frozen=True)
class AutomatedPipelineResult:
    """Combined status without changing the collection process exit result."""

    collection_exit_code: int
    run_id: str | None
    collection_status: str
    analytics_status: str
    ai_stage: AIStageResult
    collection_stdout: str
    collection_stderr: str


SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]


def run_automated_intelligence_pipeline(
    collection_args: Sequence[str],
    *,
    input_path: str | Path = DEFAULT_ANALYTICS_INPUT,
    output_path: str | Path = DEFAULT_AI_OUTPUT,
    subprocess_runner: SubprocessRunner = subprocess.run,
) -> AutomatedPipelineResult:
    """Run the unchanged daily monitor, then gate AI on its Analytics status."""

    environment = os.environ.copy()
    source_root = str(PROJECT_ROOT / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else source_root
    )
    completed = subprocess_runner(
        [sys.executable, str(DAILY_MONITOR), *collection_args],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    payload, parse_error = _collection_payload(completed.stdout)
    if payload is None:
        ai_stage = AIStageResult(
            analytics_status="unknown",
            ai_status="failed",
            input_path=str(Path(input_path).resolve(strict=False)),
            output_path=None,
            generation_mode=None,
            provider_name=None,
            error_message=parse_error,
        )
        return AutomatedPipelineResult(
            collection_exit_code=completed.returncode,
            run_id=None,
            collection_status="unknown",
            analytics_status="unknown",
            ai_stage=ai_stage,
            collection_stdout=completed.stdout,
            collection_stderr=completed.stderr,
        )

    analytics_status = str(payload.get("analytics_status", "unknown"))
    collection_status = str(
        payload.get("collection_status", payload.get("status", "unknown"))
    )
    ai_stage = run_ai_report_stage(
        analytics_status=analytics_status,
        input_path=input_path,
        output_path=output_path,
    )
    return AutomatedPipelineResult(
        collection_exit_code=completed.returncode,
        run_id=_optional_text(payload.get("run_id")),
        collection_status=collection_status,
        analytics_status=analytics_status,
        ai_stage=ai_stage,
        collection_stdout=completed.stdout,
        collection_stderr=completed.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the opt-in three-stage wrapper while preserving collection exit code."""

    parser = argparse.ArgumentParser(
        description=(
            "Run the unchanged daily monitor and generate an AI report only when "
            "its Analytics stage completes."
        )
    )
    parser.add_argument("--ai-input", type=Path, default=DEFAULT_ANALYTICS_INPUT)
    parser.add_argument("--ai-output", type=Path, default=DEFAULT_AI_OUTPUT)
    parser.add_argument("collection_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    collection_args = list(args.collection_args)
    if collection_args[:1] == ["--"]:
        collection_args = collection_args[1:]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        result = run_automated_intelligence_pipeline(
            collection_args,
            input_path=args.ai_input,
            output_path=args.ai_output,
        )
    except OSError as exc:
        logger.error("Could not launch unchanged daily monitor: %s", exc)
        return 2

    sys.stdout.write(result.collection_stdout)
    sys.stderr.write(result.collection_stderr)
    logger.info(
        "Automated intelligence status run_id=%s collection_status=%s "
        "analytics_status=%s ai_status=%s",
        result.run_id,
        result.collection_status,
        result.analytics_status,
        result.ai_stage.ai_status,
    )
    logger.info("AI stage summary=%s", json.dumps(asdict(result.ai_stage)))
    return result.collection_exit_code


def _collection_payload(stdout: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, f"Collection summary is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "Collection summary must be a JSON object"
    return payload, None


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


if __name__ == "__main__":
    raise SystemExit(main())
