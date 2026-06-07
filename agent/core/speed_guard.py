"""Tool-level timeout guard (per D004: precise per-tool timeouts)."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class ToolTimeoutError(Exception):
    """Raised when a tool exceeds its SLA budget."""


_WrappedFn = Callable[P, Coroutine[Any, Any, R]]


def with_timeout(seconds: float) -> Callable[[_WrappedFn[P, R]], _WrappedFn[P, R]]:
    """Decorate an async tool with a hard per-call timeout."""

    def decorator(fn: _WrappedFn[P, R]) -> _WrappedFn[P, R]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await asyncio.wait_for(fn(*args, **kwargs), timeout=seconds)
            except TimeoutError as exc:
                raise ToolTimeoutError(
                    f"{fn.__name__} exceeded {seconds}s SLA: "
                    "trigger partial_replan for level 2 replacement"
                ) from exc

        return wrapper

    return decorator
