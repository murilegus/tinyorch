# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, cast, override

from tinyorch._context import enter_run

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class Flow[**P, R]:
    def __init__(self, fn: Callable[P, R], *, name: str | None = None) -> None:
        self.fn: Callable[P, R] = fn
        self.name: str = name or fn.__name__
        self.is_async: bool = inspect.iscoroutinefunction(fn)
        self.__name__: str = fn.__name__
        self.__qualname__: str = fn.__qualname__
        self.__module__: str = fn.__module__
        self.__doc__: str | None = fn.__doc__
        self.__wrapped__: Callable[P, R] = fn

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        if self.is_async:
            return cast("R", self._run_async(*args, **kwargs))
        return self._run_sync(*args, **kwargs)

    def _run_sync(self, *args: P.args, **kwargs: P.kwargs) -> R:
        with enter_run(self.name):
            return self.fn(*args, **kwargs)

    async def _run_async(self, *args: P.args, **kwargs: P.kwargs) -> object:
        with enter_run(self.name):
            return await self._await(*args, **kwargs)

    # see #2
    def _await(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[object]:
        return cast("Awaitable[object]", self.fn(*args, **kwargs))

    @property
    def _key(self) -> tuple[str, str]:
        return (self.fn.__module__, self.fn.__qualname__)

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Flow):
            return NotImplemented
        return self._key == other._key

    @override
    def __hash__(self) -> int:
        return hash(self._key)
