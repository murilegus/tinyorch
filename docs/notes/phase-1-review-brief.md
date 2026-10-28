# tinyorch — Phase 1 review brief

**Mode: review only.** Do not modify, create, delete or commit any file. Do
not run `uv version`, `git tag`, `gh release` or anything that writes. You
may run read-only commands (`git log`, `uv run pytest`, `uv run basedpyright`,
`uv run ruff check`, `gh issue list`) to verify claims. Your only output is
the report described at the end.

## 1. What tinyorch is

A tiny, zero-dependency Python orchestrator for **single-node, item-level
pipelines**: a few thousand to a few million items flowing through I/O-heavy
stages on one machine, where any stage can fail halfway. Positioning: *too
small for Prefect, too finite for Flink, too painful as a bare script.*
Bounded input, streaming execution. Not a stream processor; not a Prefect
replacement.

Two purposes, equally weighted:

1. A real tool the author will dogfood on crawl + LLM pipelines.
2. A deliberate "deep Python" learning project: object model, descriptors,
   contextvars, coroutines, ParamSpec/overload typing, import/packaging.
   Design decisions are recorded as ADRs in `docs/design/`.

Repo: https://github.com/murilegus/tinyorch · PyPI: `tinyorch` (0.1.1)

## 2. State at end of phase 1

Package `src/tinyorch/`:

| File | Role |
|---|---|
| `__init__.py` | re-exports via `__all__`; `__version__` from `importlib.metadata` |
| `_api.py` | `task()` / `flow()` decorator factories, two `@overload`s each, fn positional-only |
| `_context.py` | `RunContext`, `TaskCall` (dataclasses, slots), `enter_run()` contextmanager, `current_run()` |
| `_task.py` | `Task[**P, R]`: records a `TaskCall` on the current run; sync and async paths |
| `_flow.py` | `Flow[**P, R]`: opens a `RunContext` per call; nested runs get `parent` |
| `py.typed` | PEP 561 marker |

No `_errors.py` yet (no tinyorch-specific exceptions exist). No DAG, no
parallelism, no retries, no checkpoints: tasks run in call order.

Tooling: Python ≥ 3.12, `uv` with `uv_build` backend, static version bumped
with `uv version`; ruff (`select = ["ALL"]`, documented ignores, SPDX headers
via CPY with custom regex); basedpyright strict with `failOnWarnings`;
pytest + pytest-asyncio (`auto`) + pytest-cov (branch, ≥ 95%); CI matrix
3.12/3.13; Trusted Publishing on GitHub Release; branch ruleset on `main`
(PR required, CI required, no force push); squash merges; Conventional
Commits; issues carry a type label and a phase milestone.

## 3. Decisions already made (verify the code matches)

ADR-001 — run context via `contextvars`:
- single `ContextVar[RunContext | None]`; `enter_run()` sets it, resets in
  `finally`, records `error` via `except BaseException` and `ended_at` on
  exit; nesting relies on the ContextVar token, `parent` kept for tracing.
- evidence: a module-global variant was tried and the gather isolation test
  showed cross-task overwrite.

ADR-002 — `Task`/`Flow` are objects, not wrapped functions:
- `Task[**P, R]` / `Flow[**P, R]` with `__call__`; metadata (`__name__`,
  `__qualname__`, `__module__`, `__doc__`, `__wrapped__`) copied explicitly,
  not via `functools.update_wrapper`; no `__slots__` on these classes.
- async detected with `inspect.iscoroutinefunction`; all bookkeeping lives
  inside the returned coroutine; two `cast`s remain (`Awaitable[object]`,
  `R`) — tracked in issue #2 (candidate: `SyncTask`/`AsyncTask` split).
- `__eq__`/`__hash__` on `(fn.__module__, fn.__qualname__)`.
- a `Task` called outside any flow runs the function unchanged and records
  nothing; a `Flow` does not record a `TaskCall` on its parent run.
- `TaskCall` is mutable; exceptions are re-raised unchanged.
- naming: members of package-private modules (`_context.enter_run`) carry no
  second underscore; public API is exactly `tinyorch.__all__`.
- typing tests assert at call sites (`assert_type(add(1, 2), int)`) plus
  `# pyright: ignore[...]` negative checks in never-called `_check_*`
  functions, because `ParamSpec` preserves parameter names.

## 4. What to review

Work through these in order. For each, state **finding → evidence →
severity (blocker / should-fix / nit) → suggested direction** (direction
only; no code).

### 4.1 Correctness and semantics
- Does every claim in §3 hold in the code? List any drift between ADRs and
  implementation.
- Context lifecycle: any path where `enter_run` could leak or double-reset
  (exceptions inside `yield`, `GeneratorExit`, cancellation of the awaiting
  task, `KeyboardInterrupt`)?
- Async: is there any remaining spot where bookkeeping runs at coroutine
  *creation* rather than execution? What happens if a user calls an async
  task and never awaits it?
- `is_async` detection: `functools.partial`, bound methods, callables with
  `__call__`, `async def` wrapped by another decorator — which are
  misclassified, and is the documented limitation accurate?
- Identity: are `__eq__`/`__hash__` on `(module, qualname)` safe for
  functions defined inside other functions or in `__main__`? For two
  different `Task` instances built from the same function with different
  `name=`?
- Thread safety: what breaks if a task is called from a thread
  (`run_in_executor`) today?

### 4.2 API design (with phase 2 in mind)
- Is `Task.__call__` returning `R` (a coroutine for async fns) the right
  long-term contract, or should phase 2 resolve issue #2 before adding
  `.map()` / streaming? Give a recommendation with trade-offs.
- Is `RunContext` the right place for `calls`, timing and error, or should
  per-run state be split from the "current run" pointer now, before a state
  store exists?
- What in the current public surface would be a breaking change to fix
  later? Flag anything that should change *before* 0.2.

### 4.3 Typing
- Run basedpyright. Review `tests/test_typing.py`: do the positive and
  negative checks actually guard the overloads? What is missing (e.g.
  `@flow(name=...)` on an async fn, keyword-only params, `*args`/`**kwargs`
  passthrough, `Concatenate`)?
- Are the two casts the minimum, and is `object` (not `Any`) used
  everywhere it can be?

### 4.4 Tests
- Run the suite with coverage. Which lines/branches are uncovered and are
  they worth covering?
- Which tests are tautological or test the fixture rather than the library?
- Which behaviours in §3 have **no** test?

### 4.5 Tooling, packaging, process
- `pyproject.toml`: classifiers, `license`/`license-files` (PEP 639),
  `[project.urls]`, dev groups, ruff/basedpyright/pytest/coverage config —
  anything inconsistent or missing?
- CI: is the gate complete (format, lint, types, tests, README render)?
  Anything that can go red for non-code reasons?
- Repo hygiene: `.vscode/` committed, badges, README links absolute for
  PyPI, Roadmap/Status in sync with milestones, ADR status lines accurate.
- Git history on `main`: are squash messages useful? Anything that should
  have been an issue?

### 4.6 Documentation
- README: is the three-axis comparison fair and defensible? Flag any claim
  about Prefect/Airflow/Flink that is wrong or unverified. The author has
  not used Prefect; a benchmark of Prefect on the same 10k-item scenario is
  on the todo list — say what it should measure.
- ADRs: are they written so a stranger understands the *why* in two
  minutes? What decisions were made in code but never recorded?

## 5. Phase 2 and beyond — produce a plan, do not implement

Roadmap as published:

| Phase | Scope |
|---|---|
| 2 | Pipelining: streaming tasks, bounded buffers, concurrent execution |
| 3 | Per-item checkpoints, resumable runs, pluggable state store |
| 4 | Resources with lifecycle and injection; process workers for CPU-bound tasks |
| 5 | Dogfooding on a real crawl + LLM pipeline; CLI |

Open question the author wants answered first: **phase 2 was originally
"DAG + async runner"; given the item-level positioning, should pipelining
primitives (tasks that `yield`, bounded queues between stages with
backpressure, bounded concurrency) come before any DAG, and does a static
DAG still earn its place at all?**

For phase 2 deliver:
- 2–3 candidate API shapes for pipelining (e.g. Prefect-style `.map()`,
  generator/async-iterator stage chaining, explicit `Pipeline` object), each
  with a 10-line usage sketch, the Python mechanisms it exercises
  (generators, `asyncio.Queue`, `TaskGroup`, cancellation, `contextvars`
  propagation into child tasks), and how it interacts with issue #2.
- A recommendation and the ADR(s) it would need.
- Milestones as a list of PR-sized steps with the tests each must add and
  the trap it is likely to hit (as was done in phase 1: e.g. "context reset
  before coroutine runs").
- What from phase 1 must change (breaking or not) to support it.
- Explicit non-goals for phase 2.

For phases 3–5: one paragraph each on the main design risk and what phase 2
should leave room for (e.g. per-item identity/hash for checkpoints,
resource scoping per run, picklability for process workers).

Constraints that hold for every phase: core stays stdlib-only; adapters may
use third-party libs behind Protocols; keep the core small enough to read in
one sitting (~2k lines target); every "later" becomes an issue with a label
and a milestone; every decision becomes an ADR in the same PR as the code.

## 6. Report format

Write a single Markdown report with these sections, in this order:

1. **Summary** — five bullets max: overall health, top blocker, top risk
   for phase 2.
2. **Findings** — grouped by §4.1–4.6, each as finding / evidence /
   severity / direction.
3. **Decisions to make before 0.2** — a short table: decision, options,
   recommendation, which ADR it touches.
4. **Phase 2 plan** — per §5.
5. **Phases 3–5 outlook** — per §5.
6. **Questions for the author** — anything you could not determine from the
   repo.

Be concrete and cite file paths and line numbers. Prefer fewer, sharper
findings over an exhaustive list. If you believe a phase-1 decision was
wrong, say so and why; the author asks "why" rather than accepting
conclusions, so every recommendation needs its reasoning.
