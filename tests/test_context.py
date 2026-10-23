# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

import asyncio

import pytest

from tinyorch._context import _enter_run, current_run


def test_enter_run():
    with _enter_run("a"):
        ctx = current_run()
        assert ctx is not None
        assert ctx.flow_name == "a"

    assert current_run() is None


def test_enter_run_nested():
    with _enter_run("a"):
        ctx_a = current_run()
        assert ctx_a is not None

        with _enter_run("b"):
            ctx_b = current_run()
            assert ctx_b is not None
            assert ctx_b.parent is ctx_a

        assert current_run() is ctx_a


def test_reset_ctx_on_exception():
    with pytest.raises(ValueError, match="boom"), _enter_run("a"):
        raise ValueError("boom")

    assert current_run() is None


async def test_isolated_between_tasks():
    async def worker(name: str) -> str:
        with _enter_run(name):
            await asyncio.sleep(0)
            ctx = current_run()
            assert ctx is not None
            return ctx.flow_name

    results = await asyncio.gather(worker("a"), worker("b"))
    assert results == ["a", "b"]
    assert current_run() is None
