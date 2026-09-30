from __future__ import annotations

import json
import ntpath
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


STATIC_PATH_POLICY_ENV = "JACK_PATH_POLICY_JSON"
STATIC_PATH_POLICY_VERSION = 1

# Phase 4 intentionally snapshots only environment values that are ordinary
# Windows path anchors. It does not ingest arbitrary process environment into
# the authority object.
PATH_ENVIRONMENT_KEYS = (
    "SystemRoot",
    "WINDIR",
    "SystemDrive",
    "USERPROFILE",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "TEMP",
    "TMP",
)

_ENV_PERCENT_RE = re.compile(r"%([^%]+)%")
_ENV_POWERSHELL_RE = re.compile(
    r"\$(?:env:([A-Za-z_][A-Za-z0-9_()]*)|\{env:([A-Za-z_][A-Za-z0-9_()]*)\})",
    re.IGNORECASE,
)
_ENV_BASH_RE = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_()]*)\}|([A-Za-z_][A-Za-z0-9_()]*))"
)


class RepresentedPathError(ValueError):
    """Base error for represented-path normalization."""


class RepresentedPathAmbiguous(RepresentedPathError):
    """The represented target cannot be resolved from facts owned by Jack."""


class RepresentedPathNeedsExecutorCwd(RepresentedPathAmbiguous):
    """A relative represented target requires the executor's actual cwd."""


class RepresentedPathInvalid(RepresentedPathError):
    """The represented target is structurally invalid."""


class NonFilesystemPowerShellTarget(ValueError):
    """A deterministic PowerShell provider target outside filesystem authority."""


class PathAuthorizationOutcome(str, Enum):
    """Phase-4 path classification prior to Kernel SecurityOutcome mapping."""

    ALLOW = "ALLOW"
    DENY_AND_CONTINUE = "DENY_AND_CONTINUE"
    HARD_INTERRUPT = "HARD_INTERRUPT"


@dataclass(frozen=True)
class PathAuthorizationDecision:
    outcome: PathAuthorizationOutcome
    reason: str
    canonical_target: Optional[str] = None

    @property
    def hard(self) -> bool:
        return self.outcome is PathAuthorizationOutcome.HARD_INTERRUPT


@dataclass(frozen=True)
class StructuredToolPathContract:
    """Host-owned contract for one exact structured filesystem tool."""

    tool_name: str
    path_fields: Tuple[str, ...]
    default_to_executor_cwd: bool = False


@dataclass(frozen=True)
class StructuredToolPathExtraction:
    """Deterministic extraction result for one completed tool call."""

    applicable: bool
    targets: Tuple[str, ...] = ()
    uses_executor_cwd: bool = False
    error: Optional[str] = None


@dataclass(frozen=True)
class CommandPathExtraction:
    """Bounded represented-target facts extracted from one command capability."""

    applicable: bool
    dialect: Optional[str] = None
    targets: Tuple[str, ...] = ()
    uses_executor_cwd: bool = False
    ambiguous: bool = False
    error: Optional[str] = None


_COMMAND_TEXT_KEYS = ("command", "cmd", "script")
_BASH_EXACT_TOOL_NAMES = frozenset({"bash"})
_POWERSHELL_EXACT_TOOL_NAMES = frozenset({"powershell", "pwsh"})
_GENERIC_COMMAND_TOOL_NAMES = frozenset({"shell", "terminal", "command", "exec", "cmd"})

# Simple commands whose represented filesystem scope is the executor cwd when
# no explicit target is present. This is not a claim about arbitrary child
# process behavior; Phase 4 governs represented targets, not a universal OS
# sandbox.
_BASH_CWD_SCOPED = frozenset({
    "git", "pytest", "dotnet",
})
_POWERSHELL_PATHLESS = frozenset({
    "get-process", "gps",
    "get-service", "gsv",
    "get-ciminstance",
    "get-date",
    "write-output", "echo",
    "write-host",
})
_POWERSHELL_PATH_COMMANDS = frozenset({
    "get-childitem", "gci", "dir", "ls",
    "get-content", "gc", "cat", "type",
    "set-content", "sc",
    "add-content", "ac",
    "out-file",
    "remove-item", "ri", "rm", "del",
    "copy-item", "copy", "cp",
    "move-item", "move", "mv",
    "new-item", "ni",
    "test-path",
    "resolve-path",
    "set-location", "sl", "cd",
    "push-location", "pushd",
})
_BASH_PATH_COMMANDS = frozenset({
    "cd", "pushd",
    "ls", "cat", "head", "tail",
    "rm", "rmdir", "mkdir", "touch",
    "cp", "mv",
})
_COMMAND_CONTROL = frozenset({";", "&", "&&", "||", "|"})
_REDIRECT_OPS = frozenset({">", ">>", "<"})


# Pi v0.84.2 built-in structured filesystem contracts. These are exact
# executor/tool contracts, not generic JSON-key guesses. read/edit/write require
# `path`; grep/find/ls accept optional `path` and otherwise operate on the
# executor's actual cwd.
PI_STRUCTURED_PATH_CONTRACTS = (
    StructuredToolPathContract("read", ("path",)),
    StructuredToolPathContract("edit", ("path",)),
    StructuredToolPathContract("write", ("path",)),
    StructuredToolPathContract("grep", ("path",), default_to_executor_cwd=True),
    StructuredToolPathContract("find", ("path",), default_to_executor_cwd=True),
    StructuredToolPathContract("ls", ("path",), default_to_executor_cwd=True),
)


@dataclass(frozen=True)
class RuntimePathPolicy:
    """Immutable host-owned Phase-4 path-policy snapshot for one runtime/lane."""

    runtime_id: str
    lane_id: str
    workspace_root: Optional[str]
    never_roots: Tuple[str, ...]
    _path_environment: Tuple[Tuple[str, str], ...] = field(
        repr=False,
        compare=True,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.runtime_id, str) or not self.runtime_id:
            raise ValueError("runtime_id must not be empty")
        if not isinstance(self.lane_id, str) or not self.lane_id:
            raise ValueError("lane_id must not be empty")

        if self.workspace_root is not None:
            _require_canonical_absolute(self.workspace_root, "workspace_root")

        if not isinstance(self.never_roots, tuple):
            raise TypeError("never_roots must be a tuple")

        for root in self.never_roots:
            _require_canonical_absolute(root, "never root")

        if len(self.never_roots) != len(set(self.never_roots)):
            raise ValueError("never_roots must not contain duplicates")

        if not isinstance(self._path_environment, tuple):
            raise TypeError("_path_environment must be a tuple")

        for item in self._path_environment:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], str)
            ):
                raise TypeError("_path_environment entries must be string pairs")

    @property
    def workspace_enabled(self) -> bool:
        return self.workspace_root is not None

    def path_environment(self) -> Mapping[str, str]:
        # Return a new ordinary mapping so callers cannot mutate the authority
        # snapshot retained by this frozen object.
        return dict(self._path_environment)


def _strip_one_matching_quote_layer(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1].strip()
    return text


def _normalized_environment(
    environment: Optional[Mapping[str, Any]],
) -> dict[str, str]:
    source = os.environ if environment is None else environment
    by_lower: dict[str, str] = {}

    raw_items = [(str(key), value) for key, value in source.items()]

    for key in PATH_ENVIRONMENT_KEYS:
        value = None
        for raw_key, raw_value in raw_items:
            if raw_key.lower() == key.lower():
                value = raw_value
                break
        if value is not None:
            by_lower[key.lower()] = str(value)

    return by_lower


def _expand_known_environment(
    text: str,
    environment: Mapping[str, str],
) -> str:
    result = text

    for _ in range(8):
        changed = False

        def percent(match: re.Match[str]) -> str:
            nonlocal changed
            name = match.group(1).lower()
            if name not in environment:
                raise RepresentedPathAmbiguous(
                    f"unresolved environment variable %{match.group(1)}%"
                )
            changed = True
            return environment[name]

        def powershell(match: re.Match[str]) -> str:
            nonlocal changed
            raw_name = match.group(1) or match.group(2) or ""
            name = raw_name.lower()
            if name not in environment:
                raise RepresentedPathAmbiguous(
                    f"unresolved environment variable {match.group(0)}"
                )
            changed = True
            return environment[name]

        prior = result
        result = _ENV_PERCENT_RE.sub(percent, result)
        result = _ENV_POWERSHELL_RE.sub(powershell, result)

        if result == prior or not changed:
            return result

    if _ENV_PERCENT_RE.search(result) or _ENV_POWERSHELL_RE.search(result):
        raise RepresentedPathAmbiguous(
            "environment expansion did not converge"
        )

    return result


def _normalize_known_windows_prefix(text: str) -> str:
    lowered = text.lower()

    if lowered.startswith("\\\\?\\unc\\"):
        return "\\\\" + text[8:]

    if lowered.startswith("\\\\?\\"):
        remainder = text[4:]
        drive, tail = ntpath.splitdrive(remainder)
        if drive and tail.startswith(("\\", "/")):
            return remainder
        raise RepresentedPathAmbiguous(
            "unsupported Win32 extended-length namespace"
        )

    if lowered.startswith("\\??\\"):
        remainder = text[4:]
        drive, tail = ntpath.splitdrive(remainder)
        if drive and tail.startswith(("\\", "/")):
            return remainder
        raise RepresentedPathAmbiguous(
            "unsupported NT object-manager path namespace"
        )

    if lowered.startswith("\\\\.\\"):
        raise RepresentedPathAmbiguous(
            "Win32 device namespace is not a canonical filesystem target"
        )

    return text


def _normalize_standard_win32_segment_endings(text: str) -> str:
    """Apply ordinary Win32 segment trimming without invoking the filesystem."""
    drive, tail = ntpath.splitdrive(text)
    parts = tail.split("\\")
    normalized = []
    for part in parts:
        if part in {"", ".", ".."}:
            normalized.append(part)
            continue
        trimmed = part.rstrip(" .")
        if not trimmed:
            raise RepresentedPathAmbiguous(
                "Win32 segment normalization produced an empty path component"
            )
        normalized.append(trimmed)
    return drive + "\\".join(normalized)


def _policy_object_windows_path(canonical: str) -> str:
    """Return the base filesystem object used only for policy containment."""
    _require_canonical_absolute(canonical, "canonical")
    drive, tail = ntpath.splitdrive(canonical)
    parts = tail.split("\\")
    owner_parts = []
    for part in parts:
        if not part:
            owner_parts.append(part)
            continue
        if ":" in part:
            owner = part.split(":", 1)[0]
            if not owner:
                raise RepresentedPathAmbiguous(
                    "NTFS stream target does not expose a deterministic owner object"
                )
            part = owner
        owner_parts.append(part)
    owner_path = ntpath.normcase(
        ntpath.normpath(drive + "\\".join(owner_parts))
    )
    if not _is_absolute_windows_path(owner_path):
        raise RepresentedPathAmbiguous(
            "policy comparison path did not normalize to an absolute Windows path"
        )
    return owner_path


def _is_absolute_windows_path(path: str) -> bool:
    drive, tail = ntpath.splitdrive(path)

    if drive.startswith("\\\\"):
        return bool(tail.startswith("\\") or tail == "")

    if drive:
        return tail.startswith("\\")

    return False


def _is_drive_relative(path: str) -> bool:
    drive, tail = ntpath.splitdrive(path)
    return bool(drive) and not drive.startswith("\\\\") and not tail.startswith("\\")


def _require_canonical_absolute(path: str, label: str) -> None:
    if not isinstance(path, str) or not path:
        raise ValueError(f"{label} must be a non-empty string")
    if path != ntpath.normcase(ntpath.normpath(path)):
        raise ValueError(f"{label} must already be canonical")
    if not _is_absolute_windows_path(path):
        raise ValueError(f"{label} must be absolute")


def normalize_represented_windows_path(
    value: Any,
    *,
    base_root: Optional[str] = None,
    environment: Optional[Mapping[str, Any]] = None,
) -> str:
    """Lexically normalize one represented Windows filesystem target.

    This function intentionally does not touch the filesystem. It does not call
    resolve(), stat(), realpath(), or any API that could imply object-level
    attestation. The result is only Jack's canonical represented target.
    """

    if not isinstance(value, str):
        raise RepresentedPathInvalid("represented path must be a string")

    text = _strip_one_matching_quote_layer(value)

    if not text:
        raise RepresentedPathInvalid("represented path must not be empty")

    if "\x00" in text:
        raise RepresentedPathInvalid("represented path contains NUL")

    env = _normalized_environment(environment)
    text = _expand_known_environment(text, env)
    lowered_before_prefix = text.casefold()
    extended_namespace = (
        lowered_before_prefix.startswith("\\\\?\\")
        or lowered_before_prefix.startswith("\\??\\")
    )
    text = _normalize_known_windows_prefix(text)
    text = text.replace("/", "\\")

    if _is_drive_relative(text):
        raise RepresentedPathAmbiguous(
            "drive-relative Windows path has executor-dependent meaning"
        )

    if text.startswith("\\") and not text.startswith("\\\\"):
        if base_root is None:
            raise RepresentedPathAmbiguous(
                "current-drive-rooted Windows path requires the executor's current drive"
            )
        _require_canonical_absolute(base_root, "base_root")
        base_drive, _ = ntpath.splitdrive(base_root)
        if not re.fullmatch(r"[A-Za-z]:", base_drive):
            raise RepresentedPathAmbiguous(
                "current-drive-rooted Windows path cannot derive a drive from executor cwd"
            )
        text = base_drive + text

    if not _is_absolute_windows_path(text):
        if base_root is None:
            raise RepresentedPathNeedsExecutorCwd(
                "relative represented path requires the executor's actual cwd"
            )
        _require_canonical_absolute(base_root, "base_root")
        text = ntpath.join(base_root, text)

    if not extended_namespace:
        text = _normalize_standard_win32_segment_endings(text)

    canonical = ntpath.normcase(ntpath.normpath(text))

    if not _is_absolute_windows_path(canonical):
        raise RepresentedPathAmbiguous(
            "represented path did not normalize to an absolute Windows path"
        )

    return canonical


def path_is_within_or_equal(target: str, root: str) -> bool:
    """Component-aware Windows path containment; never a string-prefix check."""

    _require_canonical_absolute(target, "target")
    _require_canonical_absolute(root, "root")

    try:
        common = ntpath.commonpath((target, root))
    except ValueError:
        return False

    return ntpath.normcase(common) == root


def _default_windows_never_roots(
    environment: Mapping[str, str],
) -> Tuple[str, ...]:
    candidates = []

    system_root = (
        environment.get("systemroot")
        or environment.get("windir")
        or ""
    ).strip()

    system_drive = environment.get("systemdrive", "").strip()

    if system_root:
        candidates.append(system_root)
        if not system_drive:
            system_drive = ntpath.splitdrive(system_root)[0]

    if system_drive:
        candidates.extend(
            (
                system_drive + r"\Boot",
                system_drive + r"\Recovery",
                system_drive + r"\System Volume Information",
            )
        )

    normalized = []
    for candidate in candidates:
        try:
            canonical = normalize_represented_windows_path(
                candidate,
                environment=environment,
            )
        except RepresentedPathError:
            continue
        if canonical not in normalized:
            normalized.append(canonical)

    return tuple(normalized)


def build_runtime_path_policy(
    *,
    runtime_id: str,
    lane_id: str,
    raw_json: str,
    host_environment: Optional[Mapping[str, Any]] = None,
) -> RuntimePathPolicy:
    """Build one immutable host-owned Phase-4 startup policy snapshot.

    `raw_json` is startup configuration transport. After construction, authority
    resides only in the returned runtime/lane-bound immutable object.
    """

    if not isinstance(raw_json, str):
        raise TypeError("raw_json must be a string")

    environment = _normalized_environment(host_environment)
    snapshot = tuple(sorted(environment.items()))

    if raw_json.strip():
        try:
            payload = json.loads(raw_json)
        except Exception:
            raise RuntimeError(
                f"{STATIC_PATH_POLICY_ENV} must contain valid JSON"
            ) from None

        if not isinstance(payload, dict):
            raise RuntimeError(
                f"{STATIC_PATH_POLICY_ENV} must be a JSON object"
            )

        if set(payload) != {"version", "workspace_root", "never_paths"}:
            raise RuntimeError(
                f"{STATIC_PATH_POLICY_ENV} has unsupported top-level fields"
            )

        version = payload.get("version")
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version != STATIC_PATH_POLICY_VERSION
        ):
            raise RuntimeError(
                f"{STATIC_PATH_POLICY_ENV} version must be "
                f"{STATIC_PATH_POLICY_VERSION}"
            )

        raw_workspace = payload.get("workspace_root")
        raw_never = payload.get("never_paths")
    else:
        raw_workspace = None
        raw_never = []

    if raw_workspace is not None and not isinstance(raw_workspace, str):
        raise RuntimeError(
            f"{STATIC_PATH_POLICY_ENV} workspace_root must be a string or null"
        )

    if not isinstance(raw_never, list) or not all(
        isinstance(item, str) for item in raw_never
    ):
        raise RuntimeError(
            f"{STATIC_PATH_POLICY_ENV} never_paths must be a list of strings"
        )

    try:
        workspace_root = (
            normalize_represented_windows_path(
                raw_workspace,
                environment=environment,
            )
            if raw_workspace is not None
            else None
        )
    except RepresentedPathError as exc:
        raise RuntimeError(
            f"{STATIC_PATH_POLICY_ENV} workspace_root is not a deterministic absolute Windows path: {exc}"
        ) from None

    never_roots = list(_default_windows_never_roots(environment))

    for raw_root in raw_never:
        try:
            canonical = normalize_represented_windows_path(
                raw_root,
                environment=environment,
            )
        except RepresentedPathError as exc:
            raise RuntimeError(
                f"{STATIC_PATH_POLICY_ENV} contains an invalid NEVER path: {exc}"
            ) from None

        if canonical not in never_roots:
            never_roots.append(canonical)

    if workspace_root is not None:
        for never_root in never_roots:
            if path_is_within_or_equal(workspace_root, never_root):
                raise RuntimeError(
                    f"{STATIC_PATH_POLICY_ENV} workspace_root cannot be inside a NEVER root"
                )

    return RuntimePathPolicy(
        runtime_id=runtime_id,
        lane_id=lane_id,
        workspace_root=workspace_root,
        never_roots=tuple(never_roots),
        _path_environment=snapshot,
    )


def _structured_tool_path_contract(
    tool_name: Any,
) -> Optional[StructuredToolPathContract]:
    if not isinstance(tool_name, str):
        return None

    normalized = tool_name.strip().casefold()

    for contract in PI_STRUCTURED_PATH_CONTRACTS:
        if normalized == contract.tool_name:
            return contract

    return None


def extract_structured_tool_paths(
    tool_name: Any,
    arguments: Any,
) -> StructuredToolPathExtraction:
    """Extract represented targets only under exact host-owned tool contracts."""

    contract = _structured_tool_path_contract(tool_name)

    if contract is None:
        return StructuredToolPathExtraction(
            applicable=False,
        )

    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except Exception:
            return StructuredToolPathExtraction(
                applicable=True,
                error="structured filesystem tool arguments are not valid JSON",
            )
    elif isinstance(arguments, dict):
        parsed = dict(arguments)
    else:
        return StructuredToolPathExtraction(
            applicable=True,
            error="structured filesystem tool arguments must be an object",
        )

    if not isinstance(parsed, dict):
        return StructuredToolPathExtraction(
            applicable=True,
            error="structured filesystem tool arguments must be an object",
        )

    targets = []

    for field_name in contract.path_fields:
        if field_name not in parsed:
            continue

        value = parsed.get(field_name)

        if not isinstance(value, str) or not value.strip():
            return StructuredToolPathExtraction(
                applicable=True,
                error="structured filesystem path field must be a non-empty string",
            )

        target = value.strip()

        if target not in targets:
            targets.append(target)

    if not targets:
        if contract.default_to_executor_cwd:
            return StructuredToolPathExtraction(
                applicable=True,
                uses_executor_cwd=True,
            )
        return StructuredToolPathExtraction(
            applicable=True,
            error="structured filesystem tool did not expose a represented path",
        )

    return StructuredToolPathExtraction(
        applicable=True,
        targets=tuple(targets),
    )


def is_command_capability_tool_name(tool_name: Any) -> bool:
    """Return whether Jack recognizes this as a command-capability tool name."""
    name = str(tool_name or "").strip().casefold()
    return name in (
        _BASH_EXACT_TOOL_NAMES
        | _POWERSHELL_EXACT_TOOL_NAMES
        | _GENERIC_COMMAND_TOOL_NAMES
    )


def _command_dialect_for_tool(
    tool_name: Any,
    explicit_dialect: Any = None,
) -> Optional[str]:
    name = str(tool_name or "").strip().casefold()
    dialect = str(explicit_dialect or "").strip().casefold()

    if name in _BASH_EXACT_TOOL_NAMES:
        return "bash" if dialect in {"", "bash"} else None

    if name in _POWERSHELL_EXACT_TOOL_NAMES:
        return "powershell" if dialect in {"", "powershell"} else None

    if name in _GENERIC_COMMAND_TOOL_NAMES:
        return dialect if dialect in {"bash", "powershell"} else None

    # A cooperating executor adapter may bind an otherwise custom command tool
    # by supplying an explicit supported dialect.
    if dialect in {"bash", "powershell"}:
        return dialect

    return None


def _command_text_from_arguments(arguments: Any) -> Tuple[Optional[str], Optional[str]]:
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except Exception:
            return None, "command tool arguments are not valid JSON"
    elif isinstance(arguments, dict):
        parsed = dict(arguments)
    else:
        return None, "command tool arguments must be an object"

    if not isinstance(parsed, dict):
        return None, "command tool arguments must be an object"

    values = [
        parsed.get(key)
        for key in _COMMAND_TEXT_KEYS
        if isinstance(parsed.get(key), str) and parsed.get(key).strip()
    ]

    if len(values) != 1:
        return None, "command tool must expose exactly one command string"

    return values[0].strip(), None


def _bash_environment_value(
    name: str,
    environment: Mapping[str, str],
) -> Optional[str]:
    key = str(name or "").strip().casefold()
    aliases = {
        "home": ("home", "userprofile"),
        "userprofile": ("userprofile", "home"),
        "windir": ("windir", "systemroot"),
        "systemroot": ("systemroot", "windir"),
    }
    for candidate in aliases.get(key, (key,)):
        value = environment.get(candidate)
        if isinstance(value, str) and value:
            return value
    return None


def _expand_known_bash_environment(
    value: str,
    environment: Mapping[str, str],
) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2) or ""
        resolved = _bash_environment_value(name, environment)
        if resolved is None:
            raise RepresentedPathAmbiguous(
                f"unknown Bash environment variable {name!r}"
            )
        return resolved

    return _ENV_BASH_RE.sub(repl, value)


def _expand_shell_home(
    value: str,
    environment: Mapping[str, str],
) -> str:
    text = str(value or "")
    if text == "~" or text.startswith("~/") or text.startswith("~\\"):
        home = _bash_environment_value("HOME", environment)
        if home is None:
            raise RepresentedPathAmbiguous("shell home directory is unavailable")
        suffix = text[1:].lstrip("/\\")
        return ntpath.join(home, suffix) if suffix else home
    if text.startswith("~"):
        raise RepresentedPathAmbiguous(
            "named-user home expansion is outside the bounded Phase-4 contract"
        )
    return text


def _map_windows_compat_bash_path(
    value: str,
    executor_platform: Optional[str],
) -> str:
    text = str(value or "")
    platform = str(executor_platform or "").strip().casefold()
    if platform not in {"win32", "windows"}:
        return text

    for pattern in (
        r"^/mnt/([A-Za-z])(?:/(.*))?$",
        r"^/cygdrive/([A-Za-z])(?:/(.*))?$",
        r"^/([A-Za-z])(?:/(.*))?$",
    ):
        match = re.match(pattern, text)
        if match:
            drive = match.group(1).upper() + ":"
            tail = match.group(2) or ""
            return drive + ("\\" + tail.replace("/", "\\") if tail else "\\")
    return text


def _normalize_powershell_filesystem_target(value: str) -> str:
    """Reduce deterministic FileSystem qualification without claiming other providers."""
    text = str(value or "").strip()
    match = re.match(
        r"(?i)^(?:(?:Microsoft\.PowerShell\.Core\\)?FileSystem)::(.+)$",
        text,
    )
    if match:
        return match.group(1)
    if (
        re.match(r"^[A-Za-z]:", text)
        or text.startswith("\\")
        or text.startswith(".")
        or text.startswith("~")
    ):
        return text
    if re.match(
        r"(?i)^(?:[A-Za-z_][A-Za-z0-9_.-]*\\)?[A-Za-z_][A-Za-z0-9_.-]*::.+$",
        text,
    ):
        raise NonFilesystemPowerShellTarget(
            "PowerShell target belongs to a non-FileSystem or unknown provider"
        )
    provider_drive = re.match(r"^([A-Za-z_][A-Za-z0-9_.-]*):", text)
    if provider_drive and len(provider_drive.group(1)) != 1:
        raise NonFilesystemPowerShellTarget(
            "PowerShell target uses a provider drive rather than a Windows drive letter"
        )
    return text


def _prepare_command_target(
    policy: RuntimePathPolicy,
    target: str,
    *,
    dialect: str,
    executor_platform: Optional[str],
) -> str:
    environment = policy.path_environment()
    prepared = _strip_token_quotes(str(target or "").strip())
    if dialect == "powershell":
        prepared = _normalize_powershell_filesystem_target(prepared)
    prepared = _expand_shell_home(
        prepared,
        environment,
    )
    if dialect == "bash":
        prepared = _expand_known_bash_environment(prepared, environment)
        prepared = _map_windows_compat_bash_path(prepared, executor_platform)
    return prepared


def _bash_command_dynamic_syntax(
    value: str,
    environment: Optional[Mapping[str, str]],
) -> bool:
    text = str(value or "")
    if environment is not None:
        normalized = _normalized_environment(environment)

        def scrub(match: re.Match[str]) -> str:
            name = match.group(1) or match.group(2) or ""
            return "" if _bash_environment_value(name, normalized) is not None else match.group(0)

        text = _ENV_BASH_RE.sub(scrub, text)

    return bool(
        re.search(
            r"`|\$\(|\$\{|\$(?:[A-Za-z_]|[0-9@*#?$!-])|"
            r"<\(|>\(|\*|\?|\[[^\]]*\]|\{|\}",
            text,
        )
    )


def _has_unresolved_dynamic_shell_syntax(
    value: str,
    dialect: str,
    *,
    environment: Optional[Mapping[str, str]] = None,
) -> bool:
    text = str(value or "")

    if dialect == "bash":
        return _bash_command_dynamic_syntax(text, environment)

    # Allow deterministic PowerShell environment references because the path
    # normalizer owns a frozen host-environment snapshot for them.
    scrubbed = _ENV_POWERSHELL_RE.sub("", text)
    return bool(
        re.search(
            r"\$\(|@\(|[{}]|`(?![\"'])|\$(?!env:|\{env:)|\*|\?|\[[^\]]*\]",
            scrubbed,
            re.IGNORECASE,
        )
    )


def _shell_tokens(command: str, dialect: str) -> Optional[list[str]]:
    import shlex

    try:
        if dialect == "bash":
            lexer = shlex.shlex(
                command,
                posix=True,
                punctuation_chars=";&|<>",
            )
        else:
            lexer = shlex.shlex(
                command,
                posix=False,
                punctuation_chars=";&|<>",
            )
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except Exception:
        return None


def _strip_token_quotes(value: str) -> str:
    token = str(value or "").strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        token = token[1:-1]
    return token


def _token_is_fully_quoted(value: str) -> bool:
    token = str(value or "").strip()
    return (
        len(token) >= 2
        and token[0] == token[-1]
        and token[0] in {"'", '"'}
    )


def _token_has_unresolved_command_expression(
    token: str,
    dialect: str,
) -> bool:
    raw = str(token or "").strip()
    if not raw or _token_is_fully_quoted(raw):
        return False

    if dialect == "bash":
        # Tilde and brace expansion materially change represented paths even
        # when no dollar-sign substitution is present.
        return raw.startswith("~") or "{" in raw or "}" in raw

    lowered = raw.casefold()
    provider_qualified = bool(
        re.match(
            r"(?i)^(?:[A-Za-z_][A-Za-z0-9_.-]*\\)?[A-Za-z_][A-Za-z0-9_.-]*::.+$",
            raw,
        )
    )

    # PowerShell expression/splatting constructs can compute a path while the
    # superficial tokens each appear harmless. Treat them as ambiguous instead
    # of pretending the bounded adapter evaluated the expression.
    return (
        raw.startswith("~")
        or raw.startswith("@")
        or raw in {"+", ","}
        or ("::" in raw and not provider_qualified)
        or raw.startswith("(")
        or raw.endswith(")")
        or raw.startswith("[")
        or raw.endswith("]")
        or lowered == "-f"
    )


def _segment_command_name(
    tokens: list[str],
    dialect: str,
) -> str:
    if not tokens:
        return ""

    filtered = []
    skip_redirect_target = False
    for token in tokens:
        if skip_redirect_target:
            skip_redirect_target = False
            continue
        if token in _REDIRECT_OPS:
            skip_redirect_target = True
            continue
        filtered.append(_strip_token_quotes(token))

    if not filtered:
        return ""

    return ntpath.basename(filtered[0]).casefold()


def _segment_changes_cwd(
    tokens: list[str],
    dialect: str,
) -> bool:
    command = _segment_command_name(tokens, dialect)

    if dialect == "bash":
        return command in {"cd", "pushd", "popd"}

    return command in {
        "set-location", "sl", "cd",
        "push-location", "pushd",
        "pop-location", "popd",
    }


def _looks_path_like_cli_value(value: str) -> bool:
    text = _strip_token_quotes(value)
    if not text:
        return False

    return bool(
        "\\" in text
        or "/" in text
        or text.startswith((".", "~"))
        or re.match(r"^[A-Za-z]:", text)
        or text.startswith("\\\\")
    )


def _path_operand_tokens(tokens: list[str]) -> Tuple[Tuple[str, ...], bool]:
    targets = []
    ambiguous = False
    index = 0

    while index < len(tokens):
        token = tokens[index]
        if token in _REDIRECT_OPS:
            if index + 1 >= len(tokens):
                return tuple(targets), True
            target = _strip_token_quotes(tokens[index + 1])
            if not target:
                return tuple(targets), True
            targets.append(target)
            index += 2
            continue
        if token.startswith("<<") or token in {">&", "<&", ">|"}:
            ambiguous = True
        index += 1

    return tuple(targets), ambiguous


def _split_command_segments(tokens: list[str]) -> list[list[str]]:
    segments = []
    current = []

    for token in tokens:
        if token in _COMMAND_CONTROL:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)

    if current:
        segments.append(current)

    return segments


def _bash_segment_targets(tokens: list[str]) -> Tuple[Tuple[str, ...], bool, bool]:
    """Return targets, uses_cwd, ambiguous for one simple Bash segment."""

    if not tokens:
        return (), False, False

    redirects, ambiguous = _path_operand_tokens(tokens)
    filtered = []
    skip_redirect_target = False

    for token in tokens:
        if skip_redirect_target:
            skip_redirect_target = False
            continue
        if token in _REDIRECT_OPS:
            skip_redirect_target = True
            continue
        filtered.append(token)

    if not filtered:
        return redirects, False, True

    command = ntpath.basename(_strip_token_quotes(filtered[0])).casefold()
    args = [_strip_token_quotes(item) for item in filtered[1:]]

    targets = list(redirects)
    uses_cwd = False

    if command == "env":
        wrapped = list(args)
        while wrapped and (
            wrapped[0].startswith("-")
            or (
                "=" in wrapped[0]
                and wrapped[0].split("=", 1)[0]
                and not wrapped[0].startswith("=")
            )
        ):
            wrapped.pop(0)

        if not wrapped:
            return tuple(targets), False, ambiguous

        found, wrapped_cwd, wrapped_ambiguous = _bash_segment_targets(
            wrapped
        )
        targets.extend(found)
        return (
            tuple(targets),
            wrapped_cwd,
            ambiguous or wrapped_ambiguous,
        )

    if command == "command":
        wrapped = list(args)
        while wrapped and wrapped[0] in {"-p", "--"}:
            wrapped.pop(0)
        if wrapped and wrapped[0] in {"-v", "-V"}:
            return tuple(targets), False, ambiguous
        if not wrapped:
            return tuple(targets), False, True
        found, wrapped_cwd, wrapped_ambiguous = _bash_segment_targets(wrapped)
        targets.extend(found)
        return tuple(targets), wrapped_cwd, ambiguous or wrapped_ambiguous

    if command in {"exec", "nohup"}:
        wrapped = list(args)
        if command == "exec":
            while wrapped:
                if wrapped[0] == "--":
                    wrapped.pop(0)
                    break
                if wrapped[0] == "-a":
                    if len(wrapped) < 3:
                        return tuple(targets), False, True
                    wrapped = wrapped[2:]
                    continue
                if wrapped[0].startswith("-"):
                    return tuple(targets), False, True
                break
        elif wrapped and wrapped[0] == "--":
            wrapped.pop(0)
        if not wrapped:
            return tuple(targets), False, True
        found, wrapped_cwd, wrapped_ambiguous = _bash_segment_targets(wrapped)
        targets.extend(found)
        return tuple(targets), wrapped_cwd, ambiguous or wrapped_ambiguous

    if command in {"bash", "sh"}:
        if not args:
            return tuple(targets), False, True
        if args[0] in {"-c", "-lc"} and len(args) >= 2:
            nested_tokens = _shell_tokens(args[1], "bash")
            if nested_tokens is None:
                return tuple(targets), False, True
            nested_ambiguous = ambiguous
            nested_cwd = False
            for nested_segment in _split_command_segments(nested_tokens):
                nested_targets, segment_cwd, segment_ambiguous = _bash_segment_targets(nested_segment)
                targets.extend(nested_targets)
                nested_cwd = nested_cwd or segment_cwd
                nested_ambiguous = nested_ambiguous or segment_ambiguous
            return tuple(targets), nested_cwd, nested_ambiguous
        return tuple(targets), False, True

    if command in {"pwd", "echo", "printf", "true", "false", "printenv", "uname", "whoami", "date"}:
        return tuple(targets), False, ambiguous

    if command in _BASH_PATH_COMMANDS:
        operands = [item for item in args if item and not item.startswith("-")]

        for item in args:
            lowered = item.casefold()
            for prefix in (
                "--target-directory=",
                "--directory=",
            ):
                if lowered.startswith(prefix):
                    targets.append(item.split("=", 1)[1])

        if command in {"cp", "mv"} and len(operands) < 2:
            ambiguous = True
        elif not operands:
            uses_cwd = True
        else:
            targets.extend(operands)
        return tuple(targets), uses_cwd, ambiguous

    if command == "git":
        uses_cwd = True
        index = 0
        while index < len(args):
            item = args[index]
            lowered = item.casefold()

            if item == "-C":
                if index + 1 >= len(args):
                    return tuple(targets), uses_cwd, True
                targets.append(args[index + 1])
                index += 2
                continue

            for prefix in ("--git-dir=", "--work-tree="):
                if lowered.startswith(prefix):
                    targets.append(item.split("=", 1)[1])
                    break

            if item in {"--git-dir", "--work-tree"}:
                if index + 1 >= len(args):
                    return tuple(targets), uses_cwd, True
                targets.append(args[index + 1])
                index += 2
                continue

            if item == "--":
                targets.extend(arg for arg in args[index + 1:] if arg)
                break

            index += 1

        subcommand = ""
        index = 0
        while index < len(args):
            item = args[index]
            lowered = item.casefold()

            if item in {"-C", "--git-dir", "--work-tree"}:
                index += 2
                continue

            if (
                lowered.startswith("--git-dir=")
                or lowered.startswith("--work-tree=")
            ):
                index += 1
                continue

            if item.startswith("-"):
                index += 1
                continue

            subcommand = lowered
            break

        if subcommand in {
            "clone",
            "config",
            "worktree",
            "archive",
            "bundle",
            "apply",
            "am",
            "format-patch",
        }:
            ambiguous = True

        for item in args:
            lowered = item.casefold()
            for prefix in (
                "--output=",
                "--output-directory=",
                "--pathspec-from-file=",
            ):
                if lowered.startswith(prefix):
                    targets.append(item.split("=", 1)[1])

        return tuple(targets), uses_cwd, ambiguous

    if command in {"pytest", "py.test"}:
        uses_cwd = True
        targets.extend(
            item for item in args
            if item and not item.startswith("-") and "::" not in item
        )
        for item in args:
            if "=" not in item or not item.startswith("-"):
                continue
            value = item.split("=", 1)[1]
            if _looks_path_like_cli_value(value):
                targets.append(value)
        return tuple(targets), uses_cwd, ambiguous

    if command in {"python", "python3", "py"}:
        if not args:
            return tuple(targets), False, True

        if args[0] in {"-m"}:
            if len(args) < 2:
                return tuple(targets), False, True
            module_name = args[1].casefold()
            if module_name in {"pytest", "unittest"}:
                uses_cwd = True
                targets.extend(
                    item for item in args[2:]
                    if item and not item.startswith("-") and "::" not in item
                )
                for item in args[2:]:
                    if "=" not in item or not item.startswith("-"):
                        continue
                    value = item.split("=", 1)[1]
                    if _looks_path_like_cli_value(value):
                        targets.append(value)
                return tuple(targets), uses_cwd, ambiguous
            return tuple(targets), False, True

        if args[0] in {"-c"}:
            return tuple(targets), False, True

        if not args[0].startswith("-"):
            targets.append(args[0])
            return tuple(targets), False, ambiguous

        return tuple(targets), False, True

    if command == "dotnet":
        if args and args[0].casefold() == "test":
            uses_cwd = True
            for item in args[1:]:
                if item.startswith("-"):
                    if "=" in item:
                        value = item.split("=", 1)[1]
                        if _looks_path_like_cli_value(value):
                            targets.append(value)
                    continue
                if (
                    "/" in item
                    or "\\" in item
                    or item.casefold().endswith((".sln", ".csproj", ".fsproj", ".vbproj"))
                ):
                    targets.append(item)
            return tuple(targets), uses_cwd, ambiguous

    return tuple(targets), False, True


def _powershell_segment_targets(tokens: list[str]) -> Tuple[Tuple[str, ...], bool, bool]:
    """Return targets, uses_cwd, ambiguous for one simple PowerShell segment."""

    if not tokens:
        return (), False, False

    redirects, ambiguous = _path_operand_tokens(tokens)

    filtered = []
    skip_redirect_target = False
    for token in tokens:
        if skip_redirect_target:
            skip_redirect_target = False
            continue
        if token in _REDIRECT_OPS:
            skip_redirect_target = True
            continue
        filtered.append(_strip_token_quotes(token))

    if not filtered:
        return redirects, False, True

    command = ntpath.basename(filtered[0]).casefold()
    args = filtered[1:]
    targets = list(redirects)
    uses_cwd = False

    if command in _POWERSHELL_PATHLESS:
        return tuple(targets), False, ambiguous

    if command in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        if not args:
            return tuple(targets), False, True
        lowered_args = [item.casefold() for item in args]
        for switch in ("-file", "-f"):
            if switch in lowered_args:
                index = lowered_args.index(switch)
                if index + 1 >= len(args):
                    return tuple(targets), False, True
                targets.append(args[index + 1])
                return tuple(targets), False, ambiguous
        for switch in ("-command", "-c"):
            if switch in lowered_args:
                index = lowered_args.index(switch)
                if index + 1 >= len(args):
                    return tuple(targets), False, True
                nested = " ".join(args[index + 1:])
                nested_tokens = _shell_tokens(nested, "powershell")
                if nested_tokens is None:
                    return tuple(targets), False, True
                nested_ambiguous = ambiguous
                nested_cwd = False
                for nested_segment in _split_command_segments(nested_tokens):
                    nested_targets, segment_cwd, segment_ambiguous = _powershell_segment_targets(nested_segment)
                    targets.extend(nested_targets)
                    nested_cwd = nested_cwd or segment_cwd
                    nested_ambiguous = nested_ambiguous or segment_ambiguous
                return tuple(targets), nested_cwd, nested_ambiguous
        return tuple(targets), False, True

    if command in _POWERSHELL_PATH_COMMANDS:
        path_switches = {
            "-path", "-literalpath", "-filepath",
            "-destination", "-dest",
        }
        source_switches = {"-source"}

        positional = []
        saw_explicit_path = False
        index = 0
        while index < len(args):
            item = args[index]
            lowered = item.casefold()

            if lowered in path_switches or lowered in source_switches:
                if index + 1 >= len(args):
                    return tuple(targets), uses_cwd, True
                targets.append(args[index + 1])
                saw_explicit_path = True
                index += 2
                continue

            if item.startswith("-"):
                index += 1
                continue

            positional.append(item)
            index += 1

        if positional:
            targets.extend(positional)
        elif saw_explicit_path:
            pass
        elif command in {"get-childitem", "gci", "dir", "ls"}:
            uses_cwd = True
        else:
            ambiguous = True

        return tuple(targets), uses_cwd, ambiguous

    # Common cross-shell developer commands use the same bounded rules.
    if command in {"git", "pytest", "py.test", "python", "python3", "py", "dotnet"}:
        return _bash_segment_targets(filtered)

    return tuple(targets), False, True


def extract_command_paths(
    tool_name: Any,
    arguments: Any,
    *,
    command_dialect: Any = None,
    environment: Optional[Mapping[str, str]] = None,
) -> CommandPathExtraction:
    """Extract represented path facts from a bounded command-language contract."""

    dialect = _command_dialect_for_tool(
        tool_name,
        command_dialect,
    )
    if dialect is None:
        return CommandPathExtraction(applicable=False)

    command, error = _command_text_from_arguments(arguments)
    if error is not None:
        return CommandPathExtraction(
            applicable=True,
            dialect=dialect,
            error=error,
        )

    if not command:
        return CommandPathExtraction(
            applicable=True,
            dialect=dialect,
            error="command text must not be empty",
        )

    dynamic_ambiguous = (
        _has_unresolved_dynamic_shell_syntax(
            command,
            dialect,
            environment=environment,
        )
        or "\n" in command
        or "\r" in command
    )

    tokens = _shell_tokens(command, dialect)
    if tokens is None:
        return CommandPathExtraction(
            applicable=True,
            dialect=dialect,
            ambiguous=True,
            error="command could not be tokenized under the bounded Phase-4 contract",
        )

    if any(
        _token_has_unresolved_command_expression(token, dialect)
        for token in tokens
    ):
        dynamic_ambiguous = True

    targets = []
    uses_cwd = False
    ambiguous = dynamic_ambiguous
    segments = _split_command_segments(tokens)

    for segment_index, segment in enumerate(segments):
        if dialect == "bash":
            found, segment_cwd, segment_ambiguous = _bash_segment_targets(segment)
        else:
            found, segment_cwd, segment_ambiguous = _powershell_segment_targets(segment)

        targets.extend(found)
        uses_cwd = uses_cwd or segment_cwd
        ambiguous = ambiguous or segment_ambiguous

        if (
            segment_index < len(segments) - 1
            and _segment_changes_cwd(segment, dialect)
        ):
            ambiguous = True

    deduped = []
    seen = set()
    for target in targets:
        if _has_unresolved_dynamic_shell_syntax(
            target,
            dialect,
            environment=environment,
        ):
            ambiguous = True
            continue
        key = target.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)

    return CommandPathExtraction(
        applicable=True,
        dialect=dialect,
        targets=tuple(deduped),
        uses_executor_cwd=uses_cwd,
        ambiguous=ambiguous,
        error=(
            "command semantics exceed the bounded Phase-4 contract"
            if ambiguous
            else None
        ),
    )


def authorize_command_tool_call(
    policy: RuntimePathPolicy,
    call: Any,
    *,
    executor_cwd: Optional[str] = None,
    command_dialect: Any = None,
    executor_platform: Optional[str] = None,
) -> PathAuthorizationDecision:
    """Authorize a command capability without pretending to be a full shell parser."""

    if not isinstance(call, dict):
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            "no command capability was identified",
        )

    function = call.get("function")
    if not isinstance(function, dict):
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            "no command capability was identified",
        )

    extraction = extract_command_paths(
        function.get("name"),
        function.get("arguments"),
        command_dialect=command_dialect,
        environment=policy.path_environment(),
    )

    if not extraction.applicable:
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            "no host-owned command contract applies",
        )

    canonical_cwd = None
    if extraction.uses_executor_cwd:
        if executor_cwd is None:
            if policy.workspace_enabled:
                return PathAuthorizationDecision(
                    PathAuthorizationOutcome.DENY_AND_CONTINUE,
                    "Workspace Lock requires the executor's actual cwd for this filesystem consequence",
                )
        else:
            cwd_decision = authorize_represented_path(policy, executor_cwd)
            if cwd_decision.outcome is not PathAuthorizationOutcome.ALLOW:
                return cwd_decision
            canonical_cwd = cwd_decision.canonical_target
    elif executor_cwd is not None:
        try:
            canonical_cwd = normalize_represented_windows_path(
                executor_cwd,
                environment=policy.path_environment(),
            )
        except RepresentedPathError:
            canonical_cwd = None

    for target in extraction.targets:
        try:
            prepared_target = _prepare_command_target(
                policy,
                target,
                dialect=extraction.dialect or "",
                executor_platform=executor_platform,
            )
        except NonFilesystemPowerShellTarget:
            continue
        except RepresentedPathAmbiguous:
            if policy.workspace_enabled:
                return PathAuthorizationDecision(
                    PathAuthorizationOutcome.DENY_AND_CONTINUE,
                    "Workspace Lock requires filesystem command targets to be deterministic",
                )
            continue

        decision = authorize_represented_path(
            policy,
            prepared_target,
            executor_cwd=canonical_cwd,
        )
        if decision.outcome is not PathAuthorizationOutcome.ALLOW:
            return decision

    if extraction.ambiguous or extraction.error:
        if policy.workspace_enabled:
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.DENY_AND_CONTINUE,
                "Workspace Lock requires command semantics to fit the bounded host-owned contract",
            )
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            "no workspace lock; ambiguous command semantics do not invent a new restriction",
        )

    return PathAuthorizationDecision(
        PathAuthorizationOutcome.ALLOW,
        "command represented targets are authorized by Phase-4 path policy",
    )


def authorize_executor_tool_call(
    policy: RuntimePathPolicy,
    call: Any,
    *,
    executor_cwd: Optional[str] = None,
    command_dialect: Any = None,
    executor_platform: Optional[str] = None,
) -> Tuple[PathAuthorizationDecision, bool]:
    """Authorize one executor call and report whether a host-owned contract applied."""

    structured = extract_structured_tool_paths(
        ((call.get("function") or {}).get("name") if isinstance(call, dict) else None),
        ((call.get("function") or {}).get("arguments") if isinstance(call, dict) else None),
    )
    if structured.applicable:
        return (
            authorize_structured_tool_call(
                policy,
                call,
                executor_cwd=executor_cwd,
                defer_relative_without_executor=False,
            ),
            True,
        )

    command = extract_command_paths(
        ((call.get("function") or {}).get("name") if isinstance(call, dict) else None),
        ((call.get("function") or {}).get("arguments") if isinstance(call, dict) else None),
        command_dialect=command_dialect,
        environment=policy.path_environment(),
    )
    if command.applicable:
        return (
            authorize_command_tool_call(
                policy,
                call,
                executor_cwd=executor_cwd,
                command_dialect=command_dialect,
                executor_platform=executor_platform,
            ),
            True,
        )

    return (
        PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            "no host-owned Phase-4 executor contract applies",
        ),
        False,
    )


def rewrite_structured_tool_call_for_workspace_release(
    policy: RuntimePathPolicy,
    call: Any,
) -> Dict[str, Any]:
    """Canonicalize structured targets before release under Workspace Lock.

    This closes the executor-cwd interpretation gap for exact structured tools:
    relative paths become absolute workspace-root-relative paths before any
    caller/executor can observe the executable call. Optional path tools that
    omitted `path` receive the locked workspace root explicitly.
    """

    if not isinstance(call, dict):
        return {}

    rewritten = json.loads(json.dumps(call))
    function = rewritten.get("function")
    if not isinstance(function, dict):
        return rewritten

    contract = _structured_tool_path_contract(function.get("name"))
    if contract is None or not policy.workspace_enabled:
        return rewritten

    raw_arguments = function.get("arguments")
    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments)
        except Exception:
            return rewritten
    elif isinstance(raw_arguments, dict):
        arguments = dict(raw_arguments)
    else:
        return rewritten

    if not isinstance(arguments, dict):
        return rewritten

    environment = policy.path_environment()
    saw_path = False

    for field_name in contract.path_fields:
        if field_name not in arguments:
            continue

        value = arguments.get(field_name)
        if not isinstance(value, str) or not value.strip():
            continue

        canonical = normalize_represented_windows_path(
            value,
            base_root=policy.workspace_root,
            environment=environment,
        )
        arguments[field_name] = canonical
        saw_path = True

    if not saw_path and contract.default_to_executor_cwd:
        arguments[contract.path_fields[0]] = policy.workspace_root

    function["arguments"] = json.dumps(
        arguments,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return rewritten


def authorize_structured_tool_call(
    policy: RuntimePathPolicy,
    call: Any,
    *,
    executor_cwd: Optional[str] = None,
    defer_relative_without_executor: bool = False,
) -> PathAuthorizationDecision:
    """Authorize a completed structured filesystem call under Phase 4.

    `executor_cwd` is an executor fact, never a model/caller policy field.
    Before executable release Jack may defer a genuinely relative represented
    target until a cooperating executor adapter supplies its actual cwd.
    """

    if not isinstance(policy, RuntimePathPolicy):
        raise TypeError("policy must be a RuntimePathPolicy")

    if not isinstance(call, dict):
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            "no structured filesystem call was identified",
        )

    function = call.get("function")

    if not isinstance(function, dict):
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            "no structured filesystem call was identified",
        )

    extraction = extract_structured_tool_paths(
        function.get("name"),
        function.get("arguments"),
    )

    if not extraction.applicable:
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            "no host-owned structured path contract applies",
        )

    if extraction.error is not None:
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.DENY_AND_CONTINUE,
            extraction.error,
        )

    if extraction.uses_executor_cwd:
        if executor_cwd is None:
            if defer_relative_without_executor:
                return PathAuthorizationDecision(
                    PathAuthorizationOutcome.ALLOW,
                    "executor cwd admission is required before execution",
                )
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.DENY_AND_CONTINUE,
                "executor cwd is required for this structured filesystem tool",
            )

        cwd_decision = authorize_represented_path(
            policy,
            executor_cwd,
        )
        if cwd_decision.outcome is not PathAuthorizationOutcome.ALLOW:
            return cwd_decision

    for represented_target in extraction.targets:
        decision = authorize_represented_path(
            policy,
            represented_target,
            executor_cwd=executor_cwd,
            defer_relative_without_executor=defer_relative_without_executor,
        )

        if decision.outcome is PathAuthorizationOutcome.HARD_INTERRUPT:
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.HARD_INTERRUPT,
                "structured tool target positively matches a NEVER root",
                decision.canonical_target,
            )

        if decision.outcome is PathAuthorizationOutcome.DENY_AND_CONTINUE:
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.DENY_AND_CONTINUE,
                "structured tool target is not authorized by Workspace Lock",
                decision.canonical_target,
            )

        if (
            decision.canonical_target is None
            and "executor cwd" in decision.reason
        ):
            return decision

    return PathAuthorizationDecision(
        PathAuthorizationOutcome.ALLOW,
        "all represented structured-tool targets are authorized",
    )


def authorize_represented_path(
    policy: RuntimePathPolicy,
    represented_path: Any,
    *,
    executor_cwd: Optional[str] = None,
    defer_relative_without_executor: bool = False,
) -> PathAuthorizationDecision:
    """Authorize only the represented target facts Phase 4 actually owns."""

    if not isinstance(policy, RuntimePathPolicy):
        raise TypeError("policy must be a RuntimePathPolicy")

    environment = policy.path_environment()
    canonical_cwd = None

    if executor_cwd is not None:
        try:
            canonical_cwd = normalize_represented_windows_path(
                executor_cwd,
                environment=environment,
            )
        except RepresentedPathError as exc:
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.DENY_AND_CONTINUE,
                f"executor cwd is not a deterministic absolute Windows path: {exc}",
            )

    try:
        canonical = normalize_represented_windows_path(
            represented_path,
            base_root=canonical_cwd,
            environment=environment,
        )
    except RepresentedPathNeedsExecutorCwd as exc:
        if defer_relative_without_executor:
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.ALLOW,
                f"executor cwd admission is required before execution: {exc}",
            )
        if policy.workspace_enabled:
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.DENY_AND_CONTINUE,
                f"workspace membership cannot be established: {exc}",
            )
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            f"no workspace lock; represented target unresolved: {exc}",
        )
    except RepresentedPathInvalid as exc:
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.DENY_AND_CONTINUE,
            f"invalid represented path: {exc}",
        )
    except RepresentedPathAmbiguous as exc:
        if policy.workspace_enabled:
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.DENY_AND_CONTINUE,
                f"workspace membership cannot be established: {exc}",
            )
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            f"no workspace lock; represented target unresolved: {exc}",
        )

    try:
        comparison_target = _policy_object_windows_path(canonical)
    except RepresentedPathAmbiguous as exc:
        if policy.workspace_enabled:
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.DENY_AND_CONTINUE,
                f"workspace membership cannot be established: {exc}",
                canonical,
            )
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.ALLOW,
            f"no workspace lock; represented target unresolved: {exc}",
            canonical,
        )

    for never_root in policy.never_roots:
        if path_is_within_or_equal(comparison_target, never_root):
            return PathAuthorizationDecision(
                PathAuthorizationOutcome.HARD_INTERRUPT,
                "represented target positively matches a NEVER root",
                canonical,
            )

    if (
        policy.workspace_root is not None
        and not path_is_within_or_equal(
            comparison_target,
            policy.workspace_root,
        )
    ):
        return PathAuthorizationDecision(
            PathAuthorizationOutcome.DENY_AND_CONTINUE,
            "represented target is outside the configured workspace",
            canonical,
        )

    return PathAuthorizationDecision(
        PathAuthorizationOutcome.ALLOW,
        "represented target is authorized by Phase-4 path policy",
        canonical,
    )
