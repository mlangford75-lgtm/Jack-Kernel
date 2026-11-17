# Run Jack with temporary, process-local cache policy environment variables.
[CmdletBinding()]
param(
    [string]$RepoPath = 'C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Kernel',
    [ValidateSet('auto', 'shared', 'prefer_isolated')]
    [string]$Policy = 'auto',
    [string]$AuxBaseUrl = '',
    [ValidateSet('off', 'llamacpp')]
    [string]$SlotAdapter = 'off',
    [ValidateRange(0, 65535)]
    [int]$PrimarySlot = 0,
    [ValidateRange(0, 65535)]
    [int]$AuxSlot = 1,
    [ValidateRange(0, 104857600)]
    [int]$MinPrimaryBytes = 8192,
    [string]$AuxStageNames = 'Agentic native pass 2'
)
$ErrorActionPreference = 'Stop'
$env:JACK_CACHE_POLICY = $Policy
$env:JACK_CACHE_AUX_BASE_URL = $AuxBaseUrl
$env:JACK_CACHE_SLOT_ADAPTER = $SlotAdapter
$env:JACK_CACHE_PRIMARY_SLOT = [string]$PrimarySlot
$env:JACK_CACHE_AUX_SLOT = [string]$AuxSlot
$env:JACK_CACHE_MIN_PRIMARY_BYTES = [string]$MinPrimaryBytes
$env:JACK_CACHE_AUX_STAGES = $AuxStageNames
$launcher = Join-Path $RepoPath 'start.bat'
if (!(Test-Path -LiteralPath $launcher)) { throw "Launcher not found: $launcher" }
Write-Host "Jack cache: policy=$Policy adapter=$SlotAdapter aux=$AuxBaseUrl" -ForegroundColor Cyan
Push-Location $RepoPath
try { & $launcher }
finally { Pop-Location }
