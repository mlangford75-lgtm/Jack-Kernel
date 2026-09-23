param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$BridgeId,

    [ValidateRange(0, 65535)]
    [int]$ControlPort = 8013,

    [bool]$PortFallback = $true,

    [string]$ControlToken = "",

    [string]$RegistryDir = ""
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command pi -ErrorAction SilentlyContinue)) {
    throw "Pi CLI was not found on PATH."
}

$env:JACK_PI_CONTROL_BRIDGE_ID = $BridgeId
$env:JACK_PI_CONTROL_PORT = [string]$ControlPort
$env:JACK_PI_CONTROL_PORT_FALLBACK = if ($PortFallback) { "1" } else { "0" }

if (-not [string]::IsNullOrWhiteSpace($ControlToken)) {
    $env:JACK_PI_CONTROL_TOKEN = $ControlToken
} else {
    Remove-Item Env:JACK_PI_CONTROL_TOKEN -ErrorAction SilentlyContinue
}

if (-not [string]::IsNullOrWhiteSpace($RegistryDir)) {
    $env:JACK_PI_CONTROL_REGISTRY_DIR = $RegistryDir
} else {
    Remove-Item Env:JACK_PI_CONTROL_REGISTRY_DIR -ErrorAction SilentlyContinue
}

Write-Host "Starting Pi worker bridge" -ForegroundColor Cyan
Write-Host "  bridge_id : $BridgeId"
Write-Host "  preferred : 127.0.0.1:$ControlPort"
Write-Host "  fallback  : $PortFallback"
if ([string]::IsNullOrWhiteSpace($ControlToken)) {
    Write-Host "  token     : from existing jack-kernel.json" -ForegroundColor Yellow
} else {
    Write-Host "  token     : explicit environment override"
}
Write-Host ""

& pi
exit $LASTEXITCODE
