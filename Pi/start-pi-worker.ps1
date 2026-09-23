param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$BridgeId,

    [ValidateRange(0, 65535)]
    [int]$ControlPort = 8013,

    [bool]$PortFallback = $true,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ControlToken,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$JackRuntimeId,

    [string]$JackApiToken = "",

    [string]$RegistryDir = "",

    [string]$JackRuntimeRegistryDir = ""
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command pi -ErrorAction SilentlyContinue)) {
    throw "Pi CLI was not found on PATH."
}

$env:JACK_PI_CONTROL_BRIDGE_ID = $BridgeId
$env:JACK_PI_CONTROL_PORT = [string]$ControlPort
$env:JACK_PI_CONTROL_PORT_FALLBACK = if ($PortFallback) { "1" } else { "0" }
$env:JACK_PI_CONTROL_TOKEN = $ControlToken

# A named worker has two independent bindings:
# 1. Jack -> worker control bridge (above)
# 2. worker model provider -> owning Jack runtime (below)
# Runtime identity, not a hard-coded port, owns the second binding.
$env:JACK_PI_JACK_RUNTIME_ID = $JackRuntimeId
Remove-Item Env:JACK_PI_JACK_URL -ErrorAction SilentlyContinue
if (-not [string]::IsNullOrWhiteSpace($JackApiToken)) {
    $env:JACK_PI_JACK_TOKEN = $JackApiToken
} else {
    Remove-Item Env:JACK_PI_JACK_TOKEN -ErrorAction SilentlyContinue
}

if (-not [string]::IsNullOrWhiteSpace($RegistryDir)) {
    $env:JACK_PI_CONTROL_REGISTRY_DIR = $RegistryDir
} else {
    Remove-Item Env:JACK_PI_CONTROL_REGISTRY_DIR -ErrorAction SilentlyContinue
}

if (-not [string]::IsNullOrWhiteSpace($JackRuntimeRegistryDir)) {
    $env:JACK_PI_JACK_RUNTIME_REGISTRY_DIR = $JackRuntimeRegistryDir
} else {
    Remove-Item Env:JACK_PI_JACK_RUNTIME_REGISTRY_DIR -ErrorAction SilentlyContinue
}

Write-Host "Starting Pi worker bridge" -ForegroundColor Cyan
Write-Host "  bridge_id       : $BridgeId"
Write-Host "  preferred       : 127.0.0.1:$ControlPort"
Write-Host "  fallback        : $PortFallback"
Write-Host "  control token   : explicit environment override"
Write-Host "  Jack runtime_id : $JackRuntimeId"
Write-Host "  Jack API token  : $(if ([string]::IsNullOrWhiteSpace($JackApiToken)) { 'none' } else { 'explicit environment override' })"
Write-Host ""

& pi
exit $LASTEXITCODE
