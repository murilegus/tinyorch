# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator


@dataclass(slots=True)
class RunContext:
    flow_name: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.monotonic)
    calls: list[TaskCall] = field(default_factory=list)
    ended_at: float | None = None
    error: BaseException | None = None
    parent: RunContext | None = None


@dataclass(slots=True)
class TaskCall:
    task_name: str
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    error: BaseException | None = None


_current: ContextVar[RunContext | None] = ContextVar("tinyorch_run", default=None)


def current_run() -> RunContext | None:
    return _current.get()


@contextmanager
def _enter_run(flow_name: str) -> Generator[RunContext, None, None]:
    ctx = RunContext(flow_name=flow_name, parent=_current.get())
    token = _current.set(ctx)
    try:
        yield ctx
    except BaseException as exc:
        ctx.error = exc
        raise
    finally:
        ctx.ended_at = time.monotonic()
        _current.reset(token)
