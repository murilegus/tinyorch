# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio

import pytest

from tinyorch._context import current_run, enter_run


def test_enter_run():
    with enter_run("f") as ctx:
        assert current_run() is ctx
        assert ctx.flow_name == "f"
        assert ctx.ended_at is None

    assert current_run() is None
    assert ctx.ended_at is not None
    assert ctx.error is None


def test_enter_run_nested():
    with enter_run("a"):
        ctx_a = current_run()
        assert ctx_a is not None

        with enter_run("b"):
            ctx_b = current_run()
            assert ctx_b is not None
            assert ctx_b.parent is ctx_a

        assert current_run() is ctx_a


def test_reset_ctx_on_exception():
    with pytest.raises(ValueError, match="boom"), enter_run("f") as ctx:
        raise ValueError("boom")

    assert current_run() is None
    assert isinstance(ctx.error, ValueError)
    assert ctx.ended_at is not None


async def test_isolated_between_tasks():
    async def worker(name: str) -> str:
        with enter_run(name):
            await asyncio.sleep(0)
            ctx = current_run()
            assert ctx is not None
            return ctx.flow_name

    results = await asyncio.gather(worker("a"), worker("b"))
    assert results == ["a", "b"]
    assert current_run() is None
