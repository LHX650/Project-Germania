@echo off
setlocal EnableExtensions DisableDelayedExpansion

for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "PIPELINE_ENTRY=%PROJECT_ROOT%\pipeline\__main__.py"
set "DATABASE_PATH=%PROJECT_ROOT%\database\project_germania_live.sqlite3"
set "RAW_OUTPUT_ROOT=%PROJECT_ROOT%\data\raw\autoscout24\daily"
set "LOG_DIRECTORY=%PROJECT_ROOT%\data\logs\scheduler"

if not exist "%PYTHON_EXE%" (
    echo Required Python executable does not exist: "%PYTHON_EXE%" 1>&2
    exit /b 2
)
if not exist "%PIPELINE_ENTRY%" (
    echo Pipeline entry point does not exist: "%PIPELINE_ENTRY%" 1>&2
    exit /b 2
)
if not exist "%DATABASE_PATH%" (
    echo Marketplace database does not exist: "%DATABASE_PATH%" 1>&2
    exit /b 2
)
if not exist "%LOG_DIRECTORY%" mkdir "%LOG_DIRECTORY%"
if errorlevel 1 (
    echo Could not create scheduler log directory: "%LOG_DIRECTORY%" 1>&2
    exit /b 2
)

for /f %%I in ('powershell.exe -NoProfile -NonInteractive -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_TIMESTAMP=%%I"
if not defined RUN_TIMESTAMP (
    echo Could not generate the scheduler log timestamp. 1>&2
    exit /b 2
)

set "LOG_FILE=%LOG_DIRECTORY%\daily_market_monitor_%RUN_TIMESTAMP%.log"
>>"%LOG_FILE%" echo [%date% %time%] Starting Project Germania intelligence pipeline.
>>"%LOG_FILE%" echo Project root: %PROJECT_ROOT%

pushd "%PROJECT_ROOT%"
"%PYTHON_EXE%" -m pipeline -- --database-path "%DATABASE_PATH%" --raw-output-root "%RAW_OUTPUT_ROOT%" %* >>"%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
popd

>>"%LOG_FILE%" echo [%date% %time%] Intelligence pipeline exit code: %EXIT_CODE%
echo Log file: "%LOG_FILE%"
exit /b %EXIT_CODE%
