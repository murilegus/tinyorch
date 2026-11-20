# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import TYPE_CHECKING

import pytest

from tinyorch._context import current_run, enter_run
from tinyorch._task import Task

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator


def _add(a: int, b: int) -> int:
    return a + b


def _boom() -> None:
    raise ValueError("boom")


async def _aboom() -> None:
    raise ValueError("boom")


async def _slow() -> None:
    await asyncio.sleep(0.01)


add = Task(_add)
boom = Task(_boom)
slow = Task(_slow)
aboom = Task(_aboom)


def test_task_run_sync():
    with enter_run("f"):
        assert add(1, 2) == 3
        ctx = current_run()
        assert ctx is not None
        assert len(ctx.calls) == 1
        call = ctx.calls[0]
        assert call.task_name == "_add"
        assert call.ended_at is not None
        assert call.error is None


def test_task_run_sync_on_exception():
    with enter_run("f"):
        with pytest.raises(ValueError, match="boom"):
            boom()

        ctx = current_run()
        assert ctx is not None
        call = ctx.calls[0]
        assert call.ended_at is not None
        assert isinstance(call.error, ValueError)


async def test_task_run_async():
    with enter_run("f"):
        await slow()
        ctx = current_run()
        assert ctx is not None
        call = ctx.calls[0]
        assert call.ended_at is not None
        assert call.ended_at - call.started_at >= 0.01


async def test_task_run_async_on_exception():
    with enter_run("f"):
        with pytest.raises(ValueError, match="boom"):
            await aboom()

        ctx = current_run()
        assert ctx is not None
        call = ctx.calls[0]
        assert call.ended_at is not None
        assert isinstance(call.error, ValueError)


def test_task_identity():
    assert add != boom
    assert add != "add"
    assert hash(add) == hash(Task(_add))
    assert Task(_add) == add
    assert len({add, add, Task(_add)}) == 1
    assert {add: "x"}[Task(_add)] == "x"


def test_task_metadata():
    assert add.name == "_add"
    assert add.__name__ == "_add"
    assert add.__wrapped__ is _add
    assert add.__doc__ == _add.__doc__
    assert inspect.signature(add) == inspect.signature(_add)
    assert add.is_async is False
    assert slow.is_async is True


def test_task_outside_run_sync():
    assert current_run() is None
    assert add(1, 2) == 3


async def test_task_outside_run_async():
    assert current_run() is None
    await slow()


def _gen() -> Iterator[int]:
    yield 1


async def _agen() -> AsyncIterator[int]:
    yield 1


class _Callable:
    def __call__(self) -> int:
        return 1

    def method(self) -> int:
        return 2

    async def amethod(self) -> int:
        return 3


@pytest.mark.parametrize("fn", [_gen, _agen])
def test_task_rejects_generator_functions(fn: Callable[..., object]):
    with pytest.raises(TypeError, match="does not support generator functions"):
        Task(fn)


@pytest.mark.parametrize("fn", [functools.partial(_add, 1), _Callable(), len])
def test_task_rejects_non_functions(fn: Callable[..., object]):
    with pytest.raises(TypeError, match="expects a function defined with"):
        Task(fn)


async def test_task_accepts_bound_methods():
    obj = _Callable()
    sync_method = Task(obj.method)
    async_method = Task(obj.amethod)

    assert sync_method.is_async is False
    assert async_method.is_async is True
    assert sync_method() == 2
    assert await async_method() == 3
