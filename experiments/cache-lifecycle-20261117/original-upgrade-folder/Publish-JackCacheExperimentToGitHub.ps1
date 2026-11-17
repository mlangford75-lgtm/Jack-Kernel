# PowerShell 5.1+: preserve the tested local cache experiment as a dedicated GitHub branch.
# Never modifies source checkout or main, never stages secrets, and never force pushes.
[CmdletBinding()]
param(
 [string]$SourceRepo = 'C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Kernel',
 [string]$UpgradeDir = 'C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Cache_Upgrade',
 [string]$WorktreePath = 'C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Kernel_Cache_GitHub',
 [string]$Branch = 'experiment/universal-cache-lifecycle-20261117',
 [switch]$SkipTests
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$expectedBase = 'f8c0abc0ae8220808267dac4ac38e4ebb9290403'
$source = (Resolve-Path -LiteralPath $SourceRepo -ErrorAction Stop).Path
if (!(Test-Path -LiteralPath (Join-Path $source '.git'))) { throw 'Source is not a Git checkout. Nothing uploaded.' }
$head = (& git -C $source rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $expectedBase) { throw "Source checkout base mismatch: $head. No changes uploaded." }

# Whitelist every component of the tested local implementation.
$code = @(
 'jack_kernel.py',
 'jack_cache_orchestrator.py',
 'jack_cache_prefix_diagnostics.py',
 'jack_stage1_cache_stability.py',
 'tests\test_jack_cache_orchestrator.py',
 'tests\test_jack_cache_prefix_diagnostics.py',
 'tests\test_jack_stage1_cache_stability.py'
)
$required = @(
 'from jack_cache_orchestrator import CacheOrchestrator',
 'from jack_cache_prefix_diagnostics import CacheBytePrefixProbe',
 'from jack_stage1_cache_stability import Stage1CacheStabilizer',
 'self._stabilize_stage1_tool_cache_system(stage_messages, messages, profile)'
)
foreach ($file in $code) {
 if (!(Test-Path -LiteralPath (Join-Path $source $file) -PathType Leaf)) { throw "Missing tested source file: $file. No changes uploaded." }
}
$kernel = [IO.File]::ReadAllText((Join-Path $source 'jack_kernel.py'))
foreach ($needle in $required) { if (!$kernel.Contains($needle)) { throw "Missing integration point: $needle. No changes uploaded." } }
if (!(Test-Path -LiteralPath $UpgradeDir -PathType Container)) { throw "Upgrade source folder is missing: $UpgradeDir" }
# Preserve every source/script/test/document displayed in the user's original
# Jack_Cache_Upgrade inventory. In addition to integrating the tested copies from
# Jack_Kernel at the repo root, archive these original distributed files unchanged.
$extras = @(
 'Install-JackCacheByteDiagnostics.ps1',
 'Install-JackCacheOrchestrator.ps1',
 'Install-JackStage1CacheStability.ps1',
 'jack_cache_orchestrator.py',
 'jack_cache_prefix_diagnostics.py',
 'jack_stage1_cache_stability.py',
 'Publish-JackCacheExperimentToGitHub.ps1',
 'README-JackCacheByteDiagnostics.md',
 'README-JackCacheOrchestrator.md',
 'README-JackStage1CacheStability.md',
 'Run-JackWithCache.ps1',
 'test_jack_cache_orchestrator.py',
 'test_jack_cache_prefix_diagnostics.py',
 'test_jack_stage1_cache_stability.py'
)
foreach ($file in $extras) {
 if (!(Test-Path -LiteralPath (Join-Path $UpgradeDir $file) -PathType Leaf)) {
  throw "Missing original cache-upgrade source file: $file. No changes uploaded."
 }
}
# Additional source-like files must never be silently omitted from the archive.
# This guard runs before any worktree is created or any branch is updated.
$known = @{}
foreach ($file in $extras) { $known[$file.ToLowerInvariant()] = $true }
$extraSources = @(Get-ChildItem -LiteralPath $UpgradeDir -File -Recurse -Force | Where-Object {
 $_.Extension.ToLowerInvariant() -in @('.ps1','.py','.md','.txt','.json','.yaml','.yml') -and
 (-not $known.ContainsKey($_.Name.ToLowerInvariant()) -or
  $_.DirectoryName.TrimEnd('\') -ne $UpgradeDir.TrimEnd('\'))
})
if ($extraSources.Count -gt 0) {
 throw "Unrecognized upgrade source files exist. Refusing incomplete archive: $($extraSources.FullName -join '; ')"
}

# Save local state evidence. This script never executes a reset/clean/checkout on SourceRepo.
$sourceStatus = @(& git -C $source status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect source status' }
$sourceHash = @{}
foreach ($file in $code) { $sourceHash[$file] = (Get-FileHash -LiteralPath (Join-Path $source $file) -Algorithm SHA256).Hash.ToLowerInvariant() }

& git -C $source remote get-url origin | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Git remote origin is missing' }
& git -C $source fetch origin "refs/heads/$($Branch):refs/remotes/origin/$($Branch)"
if ($LASTEXITCODE -ne 0) { throw "GitHub branch $Branch could not be fetched; no changes uploaded" }
$remote = (& git -C $source rev-parse "refs/remotes/origin/$Branch").Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve fetched remote branch' }
if (Test-Path -LiteralPath $WorktreePath) { throw "Destination already exists: $WorktreePath. Refusing overwrite. Source unchanged." }
$localBranch = 'experiment/cache-lifecycle-publish-20261117'
& git -C $source show-ref --verify --quiet "refs/heads/$localBranch"
if ($LASTEXITCODE -eq 0) { throw "Local branch already exists: $localBranch. Stop to avoid overwriting prior work." }
& git -C $source worktree add -b $localBranch $WorktreePath $remote
if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated worktree. Source unchanged.' }

# Copy exact original source, without altering extension, newline, encoding or content.
foreach ($file in $code) {
 $to = Join-Path $WorktreePath $file
 New-Item -ItemType Directory -Force -Path (Split-Path -Parent $to) | Out-Null
 Copy-Item -LiteralPath (Join-Path $source $file) -Destination $to -Force
 if ((Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceHash[$file]) { throw "Byte-level verification failed for $file. Nothing committed or pushed." }
}
$docsDir = Join-Path $WorktreePath 'experiments\cache-lifecycle-20261117'
$assetDir = Join-Path $docsDir 'original-upgrade-folder'
New-Item -ItemType Directory -Force -Path $assetDir | Out-Null
foreach ($file in $extras) {
 $from = Join-Path $UpgradeDir $file
 $to = Join-Path $assetDir $file
 Copy-Item -LiteralPath $from -Destination $to -Force
 if ((Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash) { throw "Upgrade source copy failed: $file. Nothing pushed." }
}

$manifest = [ordered]@{
 branch = $Branch
 baseline_commit = $expectedBase
 preserved_from = 'Original Windows checkout, copied byte-for-byte'
 changes_to_main = $false
 source_working_tree_status_entries_at_capture = @($sourceStatus).Count
 copied_files = @()
 note = 'Exact local integrated code plus complete 14-file upgrade source inventory; non-source artifacts, secrets and forensic logs excluded'
}
foreach ($file in $code) { $manifest.copied_files += [ordered]@{ path = $file.Replace('\','/'); sha256 = $sourceHash[$file] } }
foreach ($file in $extras) { $manifest.copied_files += [ordered]@{ path = ('experiments/cache-lifecycle-20261117/original-upgrade-folder/' + $file); sha256 = (Get-FileHash -LiteralPath (Join-Path $assetDir $file) -Algorithm SHA256).Hash.ToLowerInvariant() } }
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $docsDir 'manifest.json') -Encoding UTF8

Push-Location $WorktreePath
try {
 & python -m py_compile jack_kernel.py jack_cache_orchestrator.py jack_cache_prefix_diagnostics.py jack_stage1_cache_stability.py
 if ($LASTEXITCODE -ne 0) { throw 'Compilation failed. The isolated worktree remains for inspection. Nothing pushed.' }
 if (!$SkipTests) {
  & python -m pytest -q tests/test_jack_cache_orchestrator.py tests/test_jack_cache_prefix_diagnostics.py tests/test_jack_stage1_cache_stability.py
  if ($LASTEXITCODE -ne 0) { throw 'Targeted tests failed. The isolated worktree remains for inspection. Nothing pushed.' }
 }
 & git add -- jack_kernel.py jack_cache_orchestrator.py jack_cache_prefix_diagnostics.py jack_stage1_cache_stability.py tests/test_jack_cache_orchestrator.py tests/test_jack_cache_prefix_diagnostics.py tests/test_jack_stage1_cache_stability.py experiments/cache-lifecycle-20261117
 if ($LASTEXITCODE -ne 0) { throw 'git add failed. Nothing pushed.' }
 Write-Host 'Reviewing exactly the files staged for the GitHub experiment:' -ForegroundColor Cyan
 & git diff --cached --name-status
 & git diff --cached --check
 if ($LASTEXITCODE -ne 0) { throw 'Patch whitespace check failed. Nothing pushed.' }
 & git commit -m 'experiment(cache): preserve tested full cache lifecycle with all sources, tests and installers'
 if ($LASTEXITCODE -ne 0) { throw 'Commit failed. Nothing pushed.' }
 & git push origin "HEAD:refs/heads/$Branch"
 if ($LASTEXITCODE -ne 0) { throw 'GitHub push failed. Local commit remains preserved; nothing force-pushed.' }
 & git fetch origin "refs/heads/$($Branch):refs/remotes/origin/$($Branch)"
 if ($LASTEXITCODE -ne 0) { throw 'Push succeeded but remote verification fetch failed.' }
 $remoteSha = (& git rev-parse "refs/remotes/origin/$Branch").Trim()
 $localSha = (& git rev-parse HEAD).Trim()
 if ($remoteSha -ne $localSha) { throw "Remote branch HEAD ($remoteSha) differs from local commit ($localSha)." }
 Write-Host "PUBLISHED AND VERIFIED: $Branch commit $localSha" -ForegroundColor Green
 Write-Host "https://github.com/mlangford75-lgtm/Jack-Kernel/tree/$Branch" -ForegroundColor Cyan
 Write-Host 'Main, original checkout, forensic archives and local configuration were not modified.' -ForegroundColor Green
}
finally { Pop-Location }
