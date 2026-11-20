# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def check_wrappable(fn: Callable[..., object], kind: str) -> None:
    """Reject callables whose body would not run inside the bookkeeping.

    Only plain ``def`` / ``async def`` functions and bound methods are
    accepted. See ADR-002.
    """
    if not (inspect.isfunction(fn) or inspect.ismethod(fn)):
        msg = (
            f"@{kind} expects a function defined with 'def' or 'async def', "
            f"got {type(fn).__name__}; wrap it in a function first"
        )
        raise TypeError(msg)

    if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
        msg = (
            f"@{kind} does not support generator functions ({fn.__qualname__}): "
            f"the body would run after the {kind} call has already returned. "
            "Return a value from a plain 'def' or 'async def' instead"
        )
        raise TypeError(msg)
