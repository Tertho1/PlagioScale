# Wrapper to run host_autoscaler.py as a scheduled task
# Sets sane defaults for demo and writes logs to ./logs/host_autoscaler.log

if ([string]::IsNullOrWhiteSpace($Env:SCALE_UP_THRESHOLD)) { $Env:SCALE_UP_THRESHOLD = '8' }
if ([string]::IsNullOrWhiteSpace($Env:SCALE_DOWN_THRESHOLD)) { $Env:SCALE_DOWN_THRESHOLD = '3' }
if ([string]::IsNullOrWhiteSpace($Env:POLL_INTERVAL)) { $Env:POLL_INTERVAL = '2' }
if ([string]::IsNullOrWhiteSpace($Env:COOLDOWN_SECONDS)) { $Env:COOLDOWN_SECONDS = '10' }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$LogDir = Join-Path $ScriptDir 'logs'
if (-not (Test-Path $LogDir)) { New-Item -Path $LogDir -ItemType Directory | Out-Null }
$LogFile = Join-Path $LogDir 'host_autoscaler.log'

Start-Transcript -Path $LogFile -Append -Force

try {
    Write-Output "Starting PlagioScale host_autoscaler in $ScriptDir"
    Push-Location $ScriptDir
    & python (Join-Path $ScriptDir 'host_autoscaler.py')
    Pop-Location
} catch {
    Write-Error $_
} finally {
    Stop-Transcript
}
