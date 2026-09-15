$ErrorActionPreference = 'Stop'

if (-not $env:USERPROFILE) {
    throw 'Pi control bridge installation requires USERPROFILE.'
}

$Source = Join-Path $PSScriptRoot 'pi-control-bridge.ts'
$AgentDir = Join-Path $env:USERPROFILE '.pi\agent'
$DestDir = Join-Path $AgentDir 'extensions'
$Dest = Join-Path $DestDir 'pi-control-bridge.ts'
$ConfigPath = Join-Path $AgentDir 'jack-kernel.json'
$Backup = $null

if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
    throw "Missing bridge source: $Source"
}

New-Item -ItemType Directory -Path $DestDir -Force | Out-Null

if (Test-Path -LiteralPath $Dest -PathType Leaf) {
    $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $Backup = "$Dest.pre-v2-runbound-backup-$Stamp"
    Copy-Item -LiteralPath $Dest -Destination $Backup -Force
}

Copy-Item -LiteralPath $Source -Destination $Dest -Force

$InstalledHash = (Get-FileHash -LiteralPath $Dest -Algorithm SHA256).Hash.ToLowerInvariant()
$SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
if ($InstalledHash -ne $SourceHash) {
    throw 'Installed Pi control bridge hash does not match package source.'
}

# Provision only missing bridge settings. Existing provider settings, custom
# control ports, and existing control tokens remain untouched.
$Config = $null
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    try {
        $Raw = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
        $Config = $Raw | ConvertFrom-Json
    } catch {
        throw "Existing Pi configuration is not valid JSON: $ConfigPath"
    }
}
if ($null -eq $Config) {
    $Config = [pscustomobject]@{}
}

$ConfigChanged = $false
$ControlPort = $Config.PSObject.Properties['controlPort']
if ($null -eq $ControlPort) {
    $Config | Add-Member -NotePropertyName controlPort -NotePropertyValue 8013
    $ConfigChanged = $true
}

$ControlToken = $Config.PSObject.Properties['controlToken']
if ($null -eq $ControlToken -or [string]::IsNullOrWhiteSpace([string]$Config.controlToken)) {
    $Bytes = New-Object byte[] 32
    $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $Rng.GetBytes($Bytes)
    } finally {
        $Rng.Dispose()
    }
    $Token = [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    if ($null -eq $ControlToken) {
        $Config | Add-Member -NotePropertyName controlToken -NotePropertyValue $Token
    } else {
        $Config.controlToken = $Token
    }
    $ConfigChanged = $true
}

if ($ConfigChanged) {
    New-Item -ItemType Directory -Path $AgentDir -Force | Out-Null
    $Json = $Config | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($ConfigPath, $Json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}

Write-Host 'Installed Pi control bridge v2 (run-bound attribution):' -ForegroundColor Green
Write-Host "  $Dest"
if ($Backup) {
    Write-Host 'Previous bridge backed up to:' -ForegroundColor Yellow
    Write-Host "  $Backup"
}
Write-Host "SHA256: $InstalledHash"
Write-Host "Configuration: $ConfigPath"
Write-Host "Control port: $($Config.controlPort)"
Write-Host ''
if ($ConfigChanged) {
    Write-Host 'Missing bridge configuration was provisioned. Existing settings were preserved.' -ForegroundColor Green
} else {
    Write-Host 'Existing jack-kernel.json controlPort/controlToken were preserved.'
}
Write-Host 'Restart Pi after installation.'
