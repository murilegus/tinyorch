# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations

from tinyorch import Flow, Task, current_run, flow, task


def test_task_bare():
    @task
    def add(a: int, b: int) -> int:
        return a + b

    assert isinstance(add, Task)
    assert add.name == "add"
    assert add(1, 2) == 3


def test_task_with_name():
    @task(name="plus")
    def add(a: int, b: int) -> int:
        return a + b

    assert isinstance(add, Task)
    assert add.name == "plus"
    assert add.__name__ == "add"
    assert add(1, 2) == 3


def test_task_keeps_fn():
    def raw() -> None: ...

    assert task(raw).fn is raw


def test_flow_bare():
    @task
    def one() -> int:
        return 1

    @flow
    def run(n: int) -> int:
        for _ in range(n):
            one()

        ctx = current_run()
        assert ctx is not None
        return len(ctx.calls)

    assert isinstance(run, Flow)
    assert run.name == "run"
    assert run(3) == 3


def test_flow_with_name():
    @flow(name="main")
    def run() -> None: ...

    assert isinstance(run, Flow)
    assert run.name == "main"


async def test_async_decorated():
    @task
    async def one() -> int:
        return 1

    @flow(name="arun")
    async def run() -> int:
        return await one()

    assert run.is_async is True
    assert one.is_async is True
    assert await run() == 1
