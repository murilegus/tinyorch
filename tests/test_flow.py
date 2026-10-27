# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import inspect

import pytest

from tinyorch._context import RunContext, current_run
from tinyorch._flow import Flow
from tinyorch._task import Task

seen: list[RunContext | None] = []


def _add(a: int, b: int) -> int:
    return a + b


def _failing() -> None:
    seen.append(current_run())
    raise ValueError("boom")


def _inner() -> str:
    add(1, 1)
    ctx = current_run()
    assert ctx is not None
    assert ctx.parent is not None
    return ctx.parent.flow_name


def _outer() -> tuple[str, int]:
    parent_name = inner()
    ctx = current_run()
    assert ctx is not None
    return parent_name, len(ctx.calls)


def _pipeline(n: int) -> int:
    _ = sum(add(i, i) for i in range(n))
    ctx = current_run()
    assert ctx is not None
    return len(ctx.calls)


async def _arun(_: str) -> str:
    await asyncio.sleep(0)
    ctx = current_run()
    assert ctx is not None
    return ctx.run_id


async def _aslow() -> None:
    await asyncio.sleep(0)


async def _apipeline(n: int) -> int:
    for _ in range(n):
        await aslow()

    ctx = current_run()
    assert ctx is not None
    return len(ctx.calls)


add = Task(_add)
failing = Flow(_failing)
inner = Flow(_inner)
outer = Flow(_outer)
pipeline = Flow(_pipeline)

arun = Flow(_arun)
aslow = Task(_aslow)
apipeline = Flow(_apipeline)


def test_flow_records_task_calls():
    assert current_run() is None
    assert pipeline(3) == 3
    assert current_run() is None


def test_flow_propagates_and_resets():
    seen.clear()
    with pytest.raises(ValueError, match="boom"):
        failing()

    assert current_run() is None
    ctx = seen[0]
    assert ctx is not None
    assert isinstance(ctx.error, ValueError)
    assert ctx.ended_at is not None


def test_nested_flow():
    assert outer() == ("_outer", 0)


async def test_concurrent_flow_isolated():
    a, b = await asyncio.gather(arun("a"), arun("b"))
    assert a != b
    assert current_run() is None


async def test_async_flow_records_async_task_calls():
    assert current_run() is None
    assert await apipeline(3) == 3
    assert current_run() is None


def test_flow_metadata():
    assert pipeline.name == "_pipeline"
    assert pipeline.__name__ == "_pipeline"
    assert pipeline.__wrapped__ is _pipeline
    assert pipeline.__doc__ == _pipeline.__doc__
    assert inspect.signature(pipeline) == inspect.signature(_pipeline)
    assert pipeline.is_async is False
    assert arun.is_async is True


def test_flow_identity():
    assert Flow(_pipeline) == pipeline
    assert pipeline != outer
    assert pipeline != "pipeline"
    assert len({pipeline, Flow(_pipeline)}) == 1
