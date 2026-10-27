# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT
# pyright: reportUnusedFunction=false

from __future__ import annotations

from typing import assert_type

from tinyorch import flow, task


@task
def add(a: int, b: int) -> int:
    return a + b


@task(name="named")
async def fetch(_: str) -> bytes:
    return b""


@flow
def run(n: int) -> list[int]:
    return [add(i, i) for i in range(n)]


def _check_sync() -> None:
    assert_type(add(1, 2), int)
    assert_type(add(a=1, b=2), int)
    assert_type(run(3), list[int])


async def _check_async() -> None:
    assert_type(await fetch("u"), bytes)


def _check_negative() -> None:
    add("x", 2)  # pyright: ignore[reportArgumentType]
    add(1)  # pyright: ignore[reportCallIssue]
