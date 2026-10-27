# SPDX-FileCopyrightText: © 2026 Murilegus <murilegus@outlook.com>
# SPDX-License-Identifier: MIT

from importlib.metadata import version

from tinyorch._api import flow, task
from tinyorch._context import RunContext, TaskCall, current_run
from tinyorch._flow import Flow
from tinyorch._task import Task

__version__ = version("tinyorch")
__all__ = [
    "Flow",
    "RunContext",
    "Task",
    "TaskCall",
    "__version__",
    "current_run",
    "flow",
    "task",
]
