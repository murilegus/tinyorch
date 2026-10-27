# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import TYPE_CHECKING, overload

from tinyorch._flow import Flow
from tinyorch._task import Task

if TYPE_CHECKING:
    from collections.abc import Callable


@overload
def task[**P, R](fn: Callable[P, R], /) -> Task[P, R]: ...
@overload
def task[**P, R](*, name: str | None = None) -> Callable[[Callable[P, R]], Task[P, R]]: ...
def task(fn: Callable[..., object] | None = None, /, *, name: str | None = None) -> object:
    if fn is not None:
        return Task(fn, name=name)

    def decorator[**P, R](f: Callable[P, R]) -> Task[P, R]:
        return Task(f, name=name)

    return decorator


@overload
def flow[**P, R](fn: Callable[P, R], /) -> Flow[P, R]: ...
@overload
def flow[**P, R](*, name: str | None = None) -> Callable[[Callable[P, R]], Flow[P, R]]: ...
def flow(fn: Callable[..., object] | None = None, /, *, name: str | None = None) -> object:
    if fn is not None:
        return Flow(fn, name=name)

    def decorator[**P, R](f: Callable[P, R]) -> Flow[P, R]:
        return Flow(f, name=name)

    return decorator
