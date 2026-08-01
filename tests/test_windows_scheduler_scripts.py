from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = PROJECT_ROOT / "scripts" / "setup_daily_scheduler.ps1"
RUNNER_BATCH = PROJECT_ROOT / "scripts" / "run_daily_monitor.bat"


def test_scheduler_setup_uses_governed_daily_task_settings() -> None:
    script = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert '"Project Germania Daily Monitor"' in script
    assert 'Join-Path $projectRoot ".venv\\Scripts\\python.exe"' in script
    assert 'Join-Path $projectRoot "pipeline\\__main__.py"' in script
    assert 'Join-Path $projectRoot "scripts\\run_daily_monitor.bat"' in script
    assert 'Join-Path $projectRoot "database\\project_germania_live.sqlite3"' in script
    assert 'Join-Path $projectRoot "data\\raw\\autoscout24\\daily"' in script
    assert 'Join-Path $projectRoot "data\\logs\\scheduler"' in script
    assert "-WorkingDirectory $projectRoot" in script
    assert "-Daily -At ([datetime]::Today.AddHours(0))" in script
    assert "-MultipleInstances IgnoreNew" in script
    assert "SupportsShouldProcess = $true" in script
    assert "Entry point: python -m pipeline" in script
    assert "-m pipeline -- --database-path" in script
    assert "if ($null -ne $existingTask -and -not $Force)" in script
    assert "-Force:$Force" in script
    assert "Unregister-ScheduledTask" not in script


def test_batch_runner_uses_absolute_project_paths_and_preserves_exit_code() -> None:
    script = RUNNER_BATCH.read_text(encoding="utf-8")

    assert 'set "PROJECT_ROOT=%%~fI"' in script
    assert 'set "PYTHON_EXE=%PROJECT_ROOT%\\.venv\\Scripts\\python.exe"' in script
    assert 'set "PIPELINE_ENTRY=%PROJECT_ROOT%\\pipeline\\__main__.py"' in script
    assert (
        'set "DATABASE_PATH=%PROJECT_ROOT%\\database\\project_germania_live.sqlite3"'
        in script
    )
    assert (
        'set "RAW_OUTPUT_ROOT=%PROJECT_ROOT%\\data\\raw\\autoscout24\\daily"' in script
    )
    assert 'set "LOG_DIRECTORY=%PROJECT_ROOT%\\data\\logs\\scheduler"' in script
    assert '--database-path "%DATABASE_PATH%"' in script
    assert '--raw-output-root "%RAW_OUTPUT_ROOT%"' in script
    assert '"%PYTHON_EXE%" -m pipeline --' in script
    assert '"%PYTHON_EXE%" "%MONITOR_SCRIPT%"' not in script
    assert "exit /b %EXIT_CODE%" in script
