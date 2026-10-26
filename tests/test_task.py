# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import inspect

import pytest

from tinyorch._context import _enter_run, current_run
from tinyorch._task import Task


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
    with _enter_run("f"):
        assert add(1, 2) == 3
        ctx = current_run()
        assert ctx is not None
        assert len(ctx.calls) == 1
        call = ctx.calls[0]
        assert call.task_name == "_add"
        assert call.ended_at is not None
        assert call.error is None


def test_task_run_sync_on_exception():
    with _enter_run("f"):
        with pytest.raises(ValueError, match="boom"):
            boom()

        ctx = current_run()
        assert ctx is not None
        call = ctx.calls[0]
        assert call.ended_at is not None
        assert isinstance(call.error, ValueError)


async def test_task_run_async():
    with _enter_run("f"):
        await slow()
        ctx = current_run()
        assert ctx is not None
        call = ctx.calls[0]
        assert call.ended_at is not None
        assert call.ended_at - call.started_at >= 0.01


async def test_task_run_async_on_exception():
    with _enter_run("f"):
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
