$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'jack-kernel.ts'
$destDir = Join-Path $env:USERPROFILE '.pi\agent\extensions'
$dest = Join-Path $destDir 'jack-kernel.ts'

New-Item -ItemType Directory -Path $destDir -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $dest -Force

Write-Host "Installed Jack Kernel Pi context-sync extension:" -ForegroundColor Green
Write-Host "  $dest"
Write-Host ""
Write-Host "Default Jack URL: http://127.0.0.1:8001"
Write-Host "If Jack uses a different URL or API token, create:" 
Write-Host "  $env:USERPROFILE\.pi\agent\jack-kernel.json"
Write-Host 'Example: {"url":"http://127.0.0.1:8001","token":"$JACK_API_KEY"}'
Write-Host ""
Write-Host "Restart Pi or run /reload after Jack is running."
