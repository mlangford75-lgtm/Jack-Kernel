param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$RuntimeId,

    [Parameter(Mandatory = $true)]
    [ValidateSet("off", "medium", "x-high", "deep-research", "agentic", "code-debugging", "code-debugging-deep")]
    [string]$Mode,

    [ValidateRange(0, 65535)]
    [int]$Port = 8001,

    [bool]$PortFallback = $true,

    [string]$LaneId = "",

    [string]$BackendBaseUrl = "http://127.0.0.1:1234/v1",

    [string]$BackendModel = "",

    [bool]$BackendAdmissionQualified = $false,

    [string]$WorkerBridgeId = "",

    [ValidateRange(0, 65535)]
    [int]$WorkerControlPort = 0,

    [string]$WorkerControlToken = "",

    [bool]$WorkerPortFallback = $true
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($LaneId)) {
    $LaneId = $RuntimeId
}

$env:JACK_RUNTIME_ID = $RuntimeId
$env:JACK_LANE_ID = $LaneId
$env:JACK_REASONING_LEVEL = $Mode
$env:JACK_HOST = "127.0.0.1"
$env:JACK_PORT = [string]$Port
$env:JACK_PORT_FALLBACK = if ($PortFallback) { "1" } else { "0" }
$env:JACK_BACKEND_BASE_URL = $BackendBaseUrl
$env:JACK_BACKEND_MODEL = $BackendModel
$env:JACK_BACKEND_ADMISSION_QUALIFIED = if ($BackendAdmissionQualified) { "1" } else { "0" }

if (-not [string]::IsNullOrWhiteSpace($WorkerBridgeId)) {
    $env:JACK_PI_CONTROL_BRIDGE_ID = $WorkerBridgeId
} else {
    Remove-Item Env:JACK_PI_CONTROL_BRIDGE_ID -ErrorAction SilentlyContinue
}

if ($WorkerControlPort -gt 0) {
    $env:JACK_PI_CONTROL_PORT = [string]$WorkerControlPort
} else {
    Remove-Item Env:JACK_PI_CONTROL_PORT -ErrorAction SilentlyContinue
}

if (-not [string]::IsNullOrWhiteSpace($WorkerControlToken)) {
    $env:JACK_PI_CONTROL_TOKEN = $WorkerControlToken
} else {
    Remove-Item Env:JACK_PI_CONTROL_TOKEN -ErrorAction SilentlyContinue
}

$env:JACK_PI_CONTROL_PORT_FALLBACK = if ($WorkerPortFallback) { "1" } else { "0" }

$Python = $null
if (Test-Path -LiteralPath ".venv\Scripts\python.exe" -PathType Leaf) {
    $Python = (Resolve-Path ".venv\Scripts\python.exe").Path
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} else {
    throw "Jack Kernel requires Python 3."
}

Write-Host "Starting Jack lane" -ForegroundColor Cyan
Write-Host "  runtime_id : $RuntimeId"
Write-Host "  lane_id    : $LaneId"
Write-Host "  mode       : $Mode"
Write-Host "  preferred  : 127.0.0.1:$Port"
Write-Host "  fallback   : $PortFallback"
Write-Host "  backend    : $BackendBaseUrl"
if ($WorkerBridgeId) {
    Write-Host "  worker     : $WorkerBridgeId"
}
Write-Host ""

if ($Python -eq "py") {
    & py -3 "jack_secure_entrypoint.py" --serve
} else {
    & $Python "jack_secure_entrypoint.py" --serve
}

exit $LASTEXITCODE
