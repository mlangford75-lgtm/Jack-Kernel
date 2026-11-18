# Install universal, optional cache routing on a clean PR #163 checkout.
# Modifies the LOCAL checkout only. Does not push or merge to GitHub.
# PowerShell 5.1+; Python and pytest are required for validation.
[CmdletBinding()]
param(
    [string]$RepoPath = 'C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Kernel',
    [string]$BranchName = 'experiment/universal-cache-orchestrator-20261117',
    [switch]$SkipTests
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Replace-Exact {
    param([string]$Text, [string]$Old, [string]$New, [int]$Count)
    $occurrences = ([regex]::Matches($Text, [regex]::Escape($Old))).Count
    if ($occurrences -ne $Count) {
        throw "Patch refused: expected $Count occurrences, found $occurrences of anchor: $($Old.Substring(0, [Math]::Min(100,$Old.Length)))"
    }
    return $Text.Replace($Old, $New)
}

$expected = 'f8c0abc0ae8220808267dac4ac38e4ebb9290403'
$repo = (Resolve-Path -LiteralPath $RepoPath -ErrorAction Stop).Path
$source = Join-Path $repo 'jack_kernel.py'
$module = Join-Path $PSScriptRoot 'jack_cache_orchestrator.py'
$testFile = Join-Path $PSScriptRoot 'test_jack_cache_orchestrator.py'
if (!(Test-Path -LiteralPath $source) -or !(Test-Path -LiteralPath $module) -or !(Test-Path -LiteralPath $testFile)) {
    throw 'Expected jack_kernel.py and the two supplied Python files.'
}
$head = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $expected) {
    throw "Must start from PR #163 commit $expected; actual: $head"
}
$status = @(& git -C $repo status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) {
    throw 'Checkout contains uncommitted/untracked changes. Refusing to overwrite them.'
}
$original = [IO.File]::ReadAllText($source)
$newline = if ($original.Contains("`r`n")) { "`r`n" } else { "`n" }
$src = $original.Replace("`r`n", "`n")

$importReplacement = @'
from jack_tool_lifecycle import ToolLifecycleObserver
from jack_cache_orchestrator import CacheOrchestrator
'@
$src = Replace-Exact $src 'from jack_tool_lifecycle import ToolLifecycleObserver' $importReplacement 1

$initReplacement = @'
        self._agentic_previous_prompt: Optional[Dict[str, Any]] = None
        # Host-only route planner; never changes model-visible messages.
        self._cache_router = CacheOrchestrator(cfg)
'@
$src = Replace-Exact $src '        self._agentic_previous_prompt: Optional[Dict[str, Any]] = None' $initReplacement 1

$routeReplacement = @'
        cache_decision = self._cache_router.plan(profile.name, str(model), stage_messages)
        self._cache_router.apply_hint(payload, cache_decision)
        LOG.info("Jack cache routing: %s", self._cache_router.diagnostic(cache_decision))
        self._agentic_cache_prefix_probe(stage_messages, payload, profile)
'@
$src = Replace-Exact $src '        self._agentic_cache_prefix_probe(stage_messages, payload, profile)' $routeReplacement 2

$urlReplacement = @'
        url = f"{cache_decision.base_url}/chat/completions"
        primary_url = f"{cache_decision.primary_base_url}/chat/completions"
'@
$src = Replace-Exact $src '        url = f"{self.cfg.backend_base_url}/chat/completions"' $urlReplacement 2

$oldNonstream = @'
        current_payload = payload
        try:
            response = await self._client.post(url, headers=self._headers(), json=current_payload)
        except Exception as exc:
            raise HTTPException(
'@
$newNonstream = @'
        current_payload = payload
        try:
            response = await self._client.post(url, headers=self._headers(), json=current_payload)
        except httpx.ConnectError as exc:
            if not cache_decision.alternate_endpoint:
                raise HTTPException(status_code=502, detail=f"Backend connection failed: {exc}") from exc
            LOG.warning("Optional auxiliary cache endpoint unavailable; falling back to primary backend")
            self._cache_router.disable_unavailable_aux()
            url = primary_url
            response = await self._client.post(url, headers=self._headers(), json=current_payload)
        except Exception as exc:
            raise HTTPException(
'@
$src = Replace-Exact $src $oldNonstream $newNonstream 1

$beforeCompatibility = @'
        # min_p is a Qwen-recommended no-op at 0.0, but some OpenAI-compatible
'@
$compatibility = @'
        # Only retry before generation when an OPTIONAL cache feature is rejected.
        if cache_decision.alternate_endpoint and response.status_code == 404:
            LOG.warning("Optional auxiliary cache endpoint returned 404; falling back to primary backend")
            self._cache_router.disable_unavailable_aux()
            url = primary_url
            response = await self._client.post(url, headers=self._headers(), json=current_payload)
        if (response.status_code == 400 and "id_slot" in current_payload
                and ("id_slot" in response.text.lower() or "unknown" in response.text.lower()
                     or "unsupported" in response.text.lower())):
            LOG.warning("Optional backend slot hint rejected; disabling hint and retrying unchanged inference")
            self._cache_router.disable_unsupported_hint()
            current_payload = self._cache_router.strip_hint(current_payload)
            response = await self._client.post(url, headers=self._headers(), json=current_payload)

        # min_p is a Qwen-recommended no-op at 0.0, but some OpenAI-compatible
'@
$src = Replace-Exact $src $beforeCompatibility $compatibility 1

$streamOriginal = @'
        current_payload = payload
        response = await send_stream(current_payload)

        # Compatibility retry: min_p=0 is a recommended no-op but may be
'@
$streamReplacement = @'
        current_payload = payload
        try:
            response = await send_stream(current_payload)
        except httpx.ConnectError:
            if not cache_decision.alternate_endpoint:
                raise
            LOG.warning("Optional auxiliary cache endpoint unavailable; falling back to primary backend")
            self._cache_router.disable_unavailable_aux()
            url = primary_url
            response = await send_stream(current_payload)
        if cache_decision.alternate_endpoint and response.status_code == 404:
            await response.aclose()
            LOG.warning("Optional auxiliary cache endpoint returned 404; falling back to primary backend")
            self._cache_router.disable_unavailable_aux()
            url = primary_url
            response = await send_stream(current_payload)
        # Compatibility retry: min_p=0 is a recommended no-op but may be
'@
$src = Replace-Exact $src $streamOriginal $streamReplacement 1

$streamCompatOld = @'
            lower = raw.lower()
            if "min_p" in retry_payload and (
'@
$streamCompatNew = @'
            lower = raw.lower()
            if "id_slot" in retry_payload and (
                    "id_slot" in lower or "unknown" in lower or "unsupported" in lower
            ):
                self._cache_router.disable_unsupported_hint()
                retry_payload.pop("id_slot", None)
                changed = True
            if "min_p" in retry_payload and (
'@
$src = Replace-Exact $src $streamCompatOld $streamCompatNew 1

# All source changes have passed exact-anchor checks; now apply transactionally.
$newSource = $src.Replace("`n", $newline)
$utf8 = New-Object System.Text.UTF8Encoding($false)
$repoModule = Join-Path $repo 'jack_cache_orchestrator.py'
$repoTest = Join-Path $repo 'tests\test_jack_cache_orchestrator.py'
if ((Test-Path -LiteralPath $repoModule) -or (Test-Path -LiteralPath $repoTest)) {
    throw 'One or more target files already exist. Refusing to overwrite.'
}
$createdBranch = $false
$applied = $false
try {
    & git -C $repo switch -c $BranchName
    if ($LASTEXITCODE -ne 0) { throw "Unable to create local experiment branch $BranchName" }
    $createdBranch = $true
    [IO.File]::WriteAllText($source, $newSource, $utf8)
    Copy-Item -LiteralPath $module -Destination $repoModule -ErrorAction Stop
    Copy-Item -LiteralPath $testFile -Destination $repoTest -ErrorAction Stop
    $applied = $true

    Push-Location $repo
    try {
        & python -m py_compile jack_kernel.py jack_cache_orchestrator.py
        if ($LASTEXITCODE -ne 0) { throw 'Python compile failed' }
        if (!$SkipTests) {
            & python -m pytest -q tests/test_jack_cache_orchestrator.py
            if ($LASTEXITCODE -ne 0) { throw 'Cache orchestrator unit tests failed' }
        }
    }
    finally { Pop-Location }
    Write-Host "Local experiment installed successfully on $BranchName" -ForegroundColor Green
    & git -C $repo status --short --branch
    Write-Host 'Not pushed or merged. Run existing Jack regression tests before live use.'
}
catch {
    if ($applied -or $createdBranch) {
        [IO.File]::WriteAllText($source, $original, $utf8)
        Remove-Item -LiteralPath $repoModule -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $repoTest -Force -ErrorAction SilentlyContinue
    }
    throw
}
