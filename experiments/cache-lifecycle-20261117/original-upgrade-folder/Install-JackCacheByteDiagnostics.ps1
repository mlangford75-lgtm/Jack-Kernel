# Diagnostic-only update for existing Jack cache experiment. NO GitHub push/merge.
# PowerShell 5.1+ and Python. Refuses unexpected source and preserves backups.
[CmdletBinding()]
param(
    [string]$RepoPath = 'C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Kernel',
    [switch]$SkipTests
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Replace-Exact {
    param([string]$Text, [string]$Old, [string]$New, [int]$Count)
    $found = ([regex]::Matches($Text, [regex]::Escape($Old))).Count
    if ($found -ne $Count) { throw "Refusing patch: expected $Count matches, got $found for '$($Old.Substring(0, [Math]::Min(70,$Old.Length)))'" }
    return $Text.Replace($Old, $New)
}

$repo = (Resolve-Path -LiteralPath $RepoPath -ErrorAction Stop).Path
$source = Join-Path $repo 'jack_kernel.py'
$moduleDest = Join-Path $repo 'jack_cache_prefix_diagnostics.py'
$moduleSrc = Join-Path $PSScriptRoot 'jack_cache_prefix_diagnostics.py'
$testDest = Join-Path $repo 'tests\test_jack_cache_prefix_diagnostics.py'
$testSrc = Join-Path $PSScriptRoot 'test_jack_cache_prefix_diagnostics.py'

if (-not (Test-Path -LiteralPath $source) -or -not (Test-Path -LiteralPath $moduleSrc) -or -not (Test-Path -LiteralPath $testSrc)) {
    throw 'Missing jack_kernel.py or supplied diagnostic module/tests.'
}
if (-not (Test-Path -LiteralPath (Join-Path $repo 'jack_cache_orchestrator.py'))) {
    throw 'Expected installed experimental cache orchestrator; refusing to patch unrelated checkout.'
}
if ((Test-Path -LiteralPath $moduleDest) -or (Test-Path -LiteralPath $testDest)) {
    throw 'Diagnostic files already exist. Refusing a second install/overwrite.'
}
$status = @(& git -C $repo status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'git status failed' }
# Existing cache experiment is intentionally uncommitted. No clean-checkout requirement.
$original = [IO.File]::ReadAllText($source)
$nl = if ($original.Contains("`r`n")) { "`r`n" } else { "`n" }
$src = $original.Replace("`r`n", "`n")
if (-not $src.Contains('from jack_cache_orchestrator import CacheOrchestrator')) {
    throw 'Cache orchestrator import missing. Please run the original experimental installer first.'
}

$src = Replace-Exact $src 'from jack_cache_orchestrator import CacheOrchestrator' @'
from jack_cache_orchestrator import CacheOrchestrator
from jack_cache_prefix_diagnostics import CacheBytePrefixProbe
'@ 1

$src = Replace-Exact $src '        self._cache_router = CacheOrchestrator(cfg)' @'
        self._cache_router = CacheOrchestrator(cfg)
        # Host-only byte-level cache prefix diagnostics (no prompt mutation).
        self._cache_byte_probe = CacheBytePrefixProbe()
'@ 1

$oldFold = @'
        if AGENTIC_MODE:
            stage_messages = self._fold_model_facing_system_messages(stage_messages)
        sampling = self._sampling_for_profile(profile)
'@
$newFold = @'
        cache_probe_regions = ()
        if AGENTIC_MODE:
            try:
                cache_probe_regions = self._cache_byte_probe.capture_regions(
                    stage_messages, prepared_messages, stage_system
                )
            except Exception as exc:
                LOG.warning("Jack cache byte-prefix region capture unavailable (nonblocking): %s", type(exc).__name__)
            stage_messages = self._fold_model_facing_system_messages(stage_messages)
        sampling = self._sampling_for_profile(profile)
'@
$src = Replace-Exact $src $oldFold $newFold 2

$oldCall = @'
        self._agentic_cache_prefix_probe(stage_messages, payload, profile)
'@
$newCall = @'
        self._agentic_cache_prefix_probe(stage_messages, payload, profile)
        if AGENTIC_MODE:
            try:
                cache_byte_diag = self._cache_byte_probe.observe(
                    stage_messages, profile.name, cache_probe_regions
                )
                if cache_byte_diag is not None:
                    LOG.info("Jack cache byte-prefix diagnostic: %s", json.dumps(cache_byte_diag, sort_keys=True))
            except Exception as exc:
                LOG.warning("Jack cache byte-prefix diagnostic unavailable (nonblocking): %s", type(exc).__name__)
'@
$src = Replace-Exact $src $oldCall $newCall 2

if ($src -eq $original.Replace("`r`n", "`n")) { throw 'No changes generated' }
$backupDir = Join-Path $env:APPDATA 'JackKernel\backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backup = Join-Path $backupDir ("jack_kernel.py.cache-byte-backup-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($backup, $original, $utf8)
$success = $false
try {
    [IO.File]::WriteAllText($source, $src.Replace("`n", $nl), $utf8)
    Copy-Item -LiteralPath $moduleSrc -Destination $moduleDest -ErrorAction Stop
    Copy-Item -LiteralPath $testSrc -Destination $testDest -ErrorAction Stop
    Push-Location $repo
    try {
        & python -m py_compile jack_kernel.py jack_cache_orchestrator.py jack_cache_prefix_diagnostics.py
        if ($LASTEXITCODE -ne 0) { throw 'Python syntax verification failed' }
        if (-not $SkipTests) {
            & python -m pytest -q tests/test_jack_cache_orchestrator.py tests/test_jack_cache_prefix_diagnostics.py
            if ($LASTEXITCODE -ne 0) { throw 'Targeted diagnostic/cache tests failed' }
        }
    }
    finally { Pop-Location }
    $success = $true
    Write-Host "Installed local diagnostic-only patch; backup: $backup" -ForegroundColor Green
    & git -C $repo diff --stat
    Write-Host 'No GitHub push or merge occurred. Restart Jack to use diagnostics.' -ForegroundColor Yellow
}
finally {
    if (-not $success) {
        [IO.File]::WriteAllText($source, $original, $utf8)
        Remove-Item -LiteralPath $moduleDest -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $testDest -Force -ErrorAction SilentlyContinue
        Write-Warning "Installation failed. Original jack_kernel.py restored from memory. Backup: $backup"
    }
}
