from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = PROJECT_ROOT / "pipeline" / "orchestrator.py"
DAILY_MONITOR = PROJECT_ROOT / "scripts" / "daily_market_monitor.py"


def test_pipeline_delegates_collection_without_importing_protected_components() -> None:
    source = ORCHESTRATOR.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert 'PROJECT_ROOT / "scripts" / "daily_market_monitor.py"' in source
    assert DAILY_MONITOR.is_file()
    assert not any(
        module.startswith(
            (
                "germania.collectors",
                "germania.database",
                "germania.cleaning",
            )
        )
        for module in imported_modules
    )
