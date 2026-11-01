"""Attributes added to every record logged while they are bound, in the current thread or task.

Shared code binds what it knows once (a dlt pipeline run, the queue a service consumes), so call sites log
plain messages. The formatter reads the attributes when it formats a record, in the thread that logs it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from types import MappingProxyType
from typing import Any

Attributes = Mapping[str, Any]

_bound: ContextVar[Attributes] = ContextVar("power_desk_log_attributes", default=MappingProxyType({}))


def bound() -> Attributes:
    return _bound.get()


def bind(attributes: Attributes) -> Token[Attributes]:
    """Add `attributes` until `unbind` with the returned token, for hooks that start and end apart."""
    return _bound.set({**_bound.get(), **attributes})


def unbind(token: Token[Attributes]) -> None:
    _bound.reset(token)


@contextmanager
def log_context(attributes: Attributes) -> Iterator[None]:
    """Add `attributes` (OpenTelemetry-style dotted names) to every record logged in the block."""
    token = bind(attributes)
    try:
        yield
    finally:
        unbind(token)
