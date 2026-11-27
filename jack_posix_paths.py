"""POSIX represented-path semantics; no filesystem access or shell execution.

Lexical path facts are not object-level containment. In particular, symbolic
links, mount aliases, case-insensitive volumes and actual OS permissions are
owned by the executor/OS, not by this normalizer.
"""
from __future__ import annotations

import posixpath


class InvalidPosixPath(ValueError):
    pass


class UnresolvedPosixPath(ValueError):
    pass


class PosixCwdRequired(UnresolvedPosixPath):
    pass


def normalize(value, *, base_root=None):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise InvalidPosixPath("represented path must be a nonempty string without NUL")
    # Structured paths are literal; never strip spaces or expand shell syntax.
    if not value.startswith("/"):
        if base_root is None:
            raise PosixCwdRequired("relative represented path requires the executor's actual cwd")
        require_absolute(base_root)
        value = posixpath.join(base_root, value)
    # POSIX permits implementation-defined semantics for exactly two initial
    # slashes. Do not pretend this is the same namespace as a single slash.
    if value.startswith("//") and not value.startswith("///"):
        raise UnresolvedPosixPath("double-slash namespace is executor-dependent")
    return posixpath.normpath(value)


def require_absolute(value):
    if not isinstance(value, str) or not value.startswith("/") or normalize(value) != value:
        raise ValueError("path must be canonical and absolute")


def contains(target, root):
    require_absolute(target)
    require_absolute(root)
    return posixpath.commonpath((target, root)) == root
