# Experimental, LOCAL ONLY. Stabilize the initial Stage-1 system contract on
# same-work tool resumes when a PURE INSERTION has altered it.
# Never changes canonical history, Stage-2, external agent messages, or backend routing.
[CmdletBinding()]
param(
  [string]$RepoPath = 'C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Kernel',
  [switch]$SkipTests,
  [switch]$FullSuite
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Replace-Exact {
  param([string]$Text, [string]$Old, [string]$New, [int]$Expected)
  $count = ([regex]::Matches($Text, [regex]::Escape($Old))).Count
  if ($count -ne $Expected) {
    throw "Refusing source change: expected $Expected instances, found $count for: $($Old.Substring(0,[Math]::Min(90,$Old.Length)))"
  }
  return $Text.Replace($Old, $New)
}

$repo = (Resolve-Path -LiteralPath $RepoPath).Path
$source = Join-Path $repo 'jack_kernel.py'
$moduleDest = Join-Path $repo 'jack_stage1_cache_stability.py'
$testDest = Join-Path $repo 'tests\test_jack_stage1_cache_stability.py'
$moduleSrc = Join-Path $PSScriptRoot 'jack_stage1_cache_stability.py'
$testSrc = Join-Path $PSScriptRoot 'test_jack_stage1_cache_stability.py'
foreach($file in @($source,$moduleSrc,$testSrc)) {
  if (!(Test-Path -LiteralPath $file)) { throw "Required file missing: $file" }
}
if (!(Test-Path -LiteralPath (Join-Path $repo 'jack_cache_orchestrator.py'))) {
  throw 'Install the earlier cache orchestrator first.'
}
if (!(Test-Path -LiteralPath (Join-Path $repo 'jack_cache_prefix_diagnostics.py'))) {
  throw 'Install the earlier byte-prefix diagnostic experiment first.'
}
if ((Test-Path $moduleDest) -or (Test-Path $testDest)) {
  throw 'The Stage-1 stability upgrade is already present or partially installed; refusing to overwrite.'
}
$original = [IO.File]::ReadAllText($source)
$nl = if ($original.Contains("`r`n")) { "`r`n" } else { "`n" }
$src = $original.Replace("`r`n", "`n")
if (!$src.Contains('from jack_cache_orchestrator import CacheOrchestrator') -or
    !$src.Contains('from jack_cache_prefix_diagnostics import CacheBytePrefixProbe') -or
    !$src.Contains('class OpenAICompatibleBackend:')) {
  throw 'Unexpected source: this installer requires the current local cache experiment.'
}
if ($src.Contains('from jack_stage1_cache_stability import Stage1CacheStabilizer')) {
  throw 'Stage-1 stability patch already applied.'
}

$src = Replace-Exact $src 'from jack_cache_prefix_diagnostics import CacheBytePrefixProbe' @'
from jack_cache_prefix_diagnostics import CacheBytePrefixProbe
from jack_stage1_cache_stability import Stage1CacheStabilizer
'@ 1

$src = Replace-Exact $src '        self._cache_byte_probe = CacheBytePrefixProbe()' @'
        self._cache_byte_probe = CacheBytePrefixProbe()
        self._stage1_cache_stabilizer = Stage1CacheStabilizer()
'@ 1

$method = @'
    def _stabilize_stage1_tool_cache_system(
        self, stage_messages: List[Dict[str, Any]],
        history: List[Dict[str, Any]], profile: StageProfile,
    ) -> None:
        """Experimental, fail-open, source-only snapshot for SAME-work tool resumes.

        The original stage instruction is the authority for the active turn;
        a newly inserted system fragment is not silently promoted on resume.
        Never modify the canonical history or the caller-owned original.
        """
        if not AGENTIC_MODE or profile.name != "Agentic native pass 1":
            return
        try:
            owned = _agentic_forensic_turn(history)
            turn_id = getattr(owned, "turn_id", None) if owned is not None else None
            target = active_response_target(history)
            if target is None:
                return
            index = int(target["history_index"])
            # Only same-turn tool results count; earlier turns' retained tool
            # history is NOT evidence that this new request is a continuation.
            tool_continuation = any(
                isinstance(item, dict) and item.get("_jack_internal_tool_exchange")
                and item.get("role") in {"tool", "assistant"}
                for item in history[index + 1:]
            )
            report = self._stage1_cache_stabilizer.apply(
                stage=profile.name, turn_id=turn_id, messages=stage_messages,
                tool_continuation=tool_continuation,
                review_pending=_agentic_final_review_is_pending(history),
            )
            LOG.info("Jack Stage-1 system cache stability: %s", json.dumps(report, sort_keys=True))
        except Exception as exc:
            # Cache optimization is never an inference prerequisite.
            LOG.warning("Stage-1 system cache stabilization skipped (nonblocking): %s", type(exc).__name__)

'@
$src = Replace-Exact $src '    async def chat(' ($method + '    async def chat(') 1

$src = Replace-Exact $src @'
            stage_messages = self._fold_model_facing_system_messages(stage_messages)
        sampling = self._sampling_for_profile(profile)
'@ @'
            stage_messages = self._fold_model_facing_system_messages(stage_messages)
            self._stabilize_stage1_tool_cache_system(stage_messages, messages, profile)
        sampling = self._sampling_for_profile(profile)
'@ 2

$backupRoot = Join-Path $env:APPDATA 'JackKernel\backups'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$backup = Join-Path $backupRoot ('jack_kernel.py.pre-stage1-cache-stability-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($backup, $original, $utf8)
$installed = $false
try {
  [IO.File]::WriteAllText($source, $src.Replace("`n",$nl), $utf8)
  Copy-Item -LiteralPath $moduleSrc -Destination $moduleDest -ErrorAction Stop
  Copy-Item -LiteralPath $testSrc -Destination $testDest -ErrorAction Stop
  Push-Location $repo
  try {
    & python -m py_compile jack_kernel.py jack_stage1_cache_stability.py
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed' }
    if (!$SkipTests) {
      & python -m pytest -q tests/test_jack_stage1_cache_stability.py tests/test_jack_cache_prefix_diagnostics.py tests/test_jack_cache_orchestrator.py
      if ($LASTEXITCODE -ne 0) { throw 'Cache regression tests failed' }
      if ($FullSuite) {
        & python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'Full regression suite failed' }
      }
    }
  }
  finally { Pop-Location }
  $installed = $true
  Write-Host "Installed Stage-1 cache stabilization. Backup: $backup" -ForegroundColor Green
  Write-Host 'No GitHub changes made. Restart Jack for the new code.' -ForegroundColor Yellow
  & git -C $repo status --short
}
finally {
  if (!$installed) {
    [IO.File]::WriteAllText($source,$original,$utf8)
    Remove-Item -LiteralPath $moduleDest -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $testDest -Force -ErrorAction SilentlyContinue
    Write-Warning "Failed; restored original jack_kernel.py. Backup: $backup"
  }
}
