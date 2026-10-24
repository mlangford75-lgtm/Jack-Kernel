"""TAS-only per-Pi-session bearer capability; never a model instruction.

This binds one-hop host-generated R3 to a random private caller capability.
A naked session identifier, message content, and any model output are NOT
sufficient to assert ownership. Missing/malformed capabilities fail closed
when JACK_TAS_R3_OWNER_ENFORCEMENT=1 is enabled.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any
import re

_HEADER = 'x-jack-tas-session-capability'
_current: ContextVar[str | None] = ContextVar('jack_tas_r3_session_owner', default=None)


def parse_session_capability(headers: Any) -> str | None:
    """Accept precisely one 256-bit hex bearer capability, never raw session ID."""
    value = headers.get(_HEADER) if headers is not None else None
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', value):
        raise ValueError('Invalid TAS session capability')
    return value.lower()


def current_owner() -> str | None:
    return _current.get()


def set_current_owner(value: str | None) -> Token:
    return _current.set(value)


def reset_current_owner(token: Token) -> None:
    _current.reset(token)
