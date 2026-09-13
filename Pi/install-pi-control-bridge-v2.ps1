$ErrorActionPreference = 'Stop'

if (-not $env:USERPROFILE) {
    throw 'Pi control bridge installation requires USERPROFILE.'
}

$Source = Join-Path $PSScriptRoot 'pi-control-bridge.ts'
$DestDir = Join-Path $env:USERPROFILE '.pi\agent\extensions'
$Dest = Join-Path $DestDir 'pi-control-bridge.ts'
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

Write-Host 'Installed Pi control bridge v2 (run-bound attribution):' -ForegroundColor Green
Write-Host "  $Dest"
if ($Backup) {
    Write-Host 'Previous bridge backed up to:' -ForegroundColor Yellow
    Write-Host "  $Backup"
}
Write-Host "SHA256: $InstalledHash"
Write-Host ''
Write-Host 'Restart Pi after installation. The existing jack-kernel.json controlPort/controlToken is preserved.'
