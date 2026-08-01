[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$TaskName = "Project Germania Daily Monitor",
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pipelineEntry = Join-Path $projectRoot "pipeline\__main__.py"
$runnerBatch = Join-Path $projectRoot "scripts\run_daily_monitor.bat"
$databasePath = Join-Path $projectRoot "database\project_germania_live.sqlite3"
$rawOutputRoot = Join-Path $projectRoot "data\raw\autoscout24\daily"
$logDirectory = Join-Path $projectRoot "data\logs\scheduler"
$schedulerLogFile = Join-Path $logDirectory "daily_market_monitor_scheduler.log"

foreach ($requiredFile in @($pythonPath, $pipelineEntry, $runnerBatch, $databasePath)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required file does not exist: $requiredFile"
    }
}

foreach ($requiredCommand in @(
    "Get-ScheduledTask",
    "New-ScheduledTaskAction",
    "New-ScheduledTaskPrincipal",
    "New-ScheduledTaskSettingsSet",
    "New-ScheduledTaskTrigger",
    "Register-ScheduledTask"
)) {
    if (-not (Get-Command $requiredCommand -ErrorAction SilentlyContinue)) {
        throw "Windows ScheduledTasks command is unavailable: $requiredCommand"
    }
}

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $existingTask -and -not $Force) {
    throw "Scheduled task already exists: $TaskName. Re-run with -Force to update it."
}

$actionArguments = (
    '/d /s /c ""{0}" -m pipeline -- --database-path "{1}" ' +
    '--raw-output-root "{2}" >> "{3}" 2>&1"'
) -f $pythonPath, $databasePath, $rawOutputRoot, $schedulerLogFile
$action = New-ScheduledTaskAction `
    -Execute $env:ComSpec `
    -Argument $actionArguments `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(0))
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Write-Host "Task: $TaskName"
Write-Host "Schedule: daily at 00:00 in the Windows local time zone"
Write-Host "Start in: $projectRoot"
Write-Host "Python: $pythonPath"
Write-Host "Entry point: python -m pipeline"
Write-Host "Database: $databasePath"
Write-Host "Raw output: $rawOutputRoot"
Write-Host "Logs: $logDirectory"
Write-Host "Action arguments: $actionArguments"
Write-Host "Multiple instances: IgnoreNew"

if ($PSCmdlet.ShouldProcess($logDirectory, "Create scheduler log directory")) {
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
}

if ($PSCmdlet.ShouldProcess($TaskName, "Register daily Windows scheduled task")) {
    $registeredTask = Register-ScheduledTask `
        -TaskName $TaskName `
        -Description "Run the Project Germania production intelligence pipeline." `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Force:$Force

    Write-Host "Scheduled task registered: $($registeredTask.TaskName)"
}
