# 🔀 tinyorch

[![ci](https://github.com/murilegus/tinyorch/actions/workflows/ci.yml/badge.svg)](https://github.com/murilegus/tinyorch/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tinyorch)](https://pypi.org/project/tinyorch/)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A tiny, zero-dependency orchestrator for single-node, item-level pipelines.

🚧 **Status**: Phase 1 complete — `@task` / `@flow` run sequentially with run
tracking. No DAG, parallelism, retries or checkpoints yet; those are phase 2–3.


## 🚀 Quickstart

```bash
pip install tinyorch
```

```python
import asyncio
from tinyorch import task, flow, current_run


@task
async def fetch(url: str) -> str:
    await asyncio.sleep(0.1)  # pretend to hit the network
    return f"<html>{url}</html>"


@task
def parse(html: str) -> list[str]:
    return html.split()


@flow
async def crawl(urls: list[str]) -> int:
    for url in urls:
        parse(await fetch(url))
    run = current_run()
    return len(run.calls) if run else 0


print(asyncio.run(crawl(["a", "b", "c"])))  # 6 task calls recorded
```

A `@task` is a plain callable with metadata: outside a flow it just runs.
Inside a `@flow`, every call is recorded on the current `RunContext`
(`current_run()`), which also tracks the flow's own timing and failure.
Sync and async functions both work; the wrapped signature is preserved for
type checkers.


## 🤔 Why tinyorch?

tinyorch is for the job that is **too small for Prefect, too finite for Flink,
and too painful as a bare script**: a few thousand to a few million items
(URLs, documents, records) flowing through I/O-heavy stages on one machine,
where any stage can fail halfway.

Three families of tools already exist for pipelines. Each is right for its
sweet spot and awkward outside it:

| | Workflow orchestrators<br>Airflow · Prefect · Dagster | Stream processors<br>Flink · Bytewax · Faust | Bare script<br>`asyncio.gather` + `tenacity` | **tinyorch** |
|---|---|---|---|---|
| Input | bounded, per task | **unbounded**, per event | bounded | bounded, per item |
| Execution | one stage finishes before the next starts | continuous | ad hoc | pipelined, bounded buffers |
| Resume after crash | per task / per run | cluster checkpoints | hand-rolled or none | per item |
| Shared resources (browser, LLM client) | per process, awkward | n/a | manual | first-class |
| Infra | server + database | cluster | none | none |
| Sweet spot | multi-team, multi-machine DAGs | 24/7 event streams | one-off | one node, 10³–10⁶ items, crash-prone I/O |

The architectural difference tinyorch is built around: in a stage-at-a-time
orchestrator, data crossing a task boundary is materialized (in RAM or an
object store) before the next stage starts. tinyorch instead pipelines items
through stages with bounded buffers and checkpoints each item, so a rerun only
does what is left and memory stays flat regardless of input size.

![Stage-at-a-time orchestrators vs tinyorch pipelining](docs/assets/stage-vs-pipelined.svg)

**tinyorch is not a stream processor.** It takes a *bounded* input and
executes it with streaming semantics. There are no windows, no event time, no
unbounded sources, no distributed state. If you need those, use Flink.

**It is not a replacement for Prefect or Airflow either.** When the pipeline
outgrows one machine or one team, those are the tools to move to; tinyorch
aims to make that boundary obvious rather than blurry.


## 🏗️ Architecture

The core is stdlib-only and defines Protocols; everything that touches the
outside world (state stores, browsers, LLM clients, CLI) is an adapter shipped
as an optional extra.

![tinyorch architecture](docs/assets/architecture.svg)


## 🚫 Non-goals

- **Multi-node scheduling** or a long-running scheduler service — one process,
  one machine, started by cron, a Cloud Run Job or your own code
- **Unbounded / event-time stream processing** — input is finite; no windows,
  watermarks or distributed state
- **A full web UI** with authentication and multi-tenancy — a local, read-only
  run viewer is planned as an optional extra
- **Time-based backfills** in the Airflow sense — runs are keyed by input, not
  by schedule interval


## 📄 Documentation

- [`docs/design/`](docs/design/) — design decisions are recorded as ADRs.


## 🎫 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
