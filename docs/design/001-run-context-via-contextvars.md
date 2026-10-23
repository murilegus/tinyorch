# ADR-001: Run context is propagated with `contextvars`

- Status: accepted
- Date: 2026-10-24
- Scope: `tinyorch._context`

## Context

A task running inside a flow needs to know which run it belongs to, without
the user threading a `run` argument through every call. Something must hold
the "current run" implicitly: the flow sets it on entry, tasks read it.

tinyorch runs many flows and tasks concurrently on a single thread with
asyncio, and may later run tasks in worker threads or processes. The holder
must therefore be isolated per asyncio task, not just per thread.

## Options considered

1. **Module-level global** (`_current_run: RunContext | None`).
   Simplest. Breaks as soon as two flows run concurrently: flow B overwrites
   flow A's context, and A's tasks silently record against B's run. No
   exception, just wrong data.
2. **`threading.local`**.
   Isolated per thread, but asyncio multiplexes many coroutines on one
   thread, so it has the same overwrite problem as option 1.
3. **`contextvars.ContextVar`**.
   Isolated per asyncio task and per thread. `asyncio.create_task` copies the
   current context into the new task, so a child task sees its parent's run
   and a sibling task cannot overwrite it. This is the mechanism the stdlib
   itself uses (`decimal`, `asyncio`).

## Decision

Use a single `ContextVar[RunContext | None]`, set by `_enter_run()` and read
by `current_run()`.

- `_enter_run()` is a `@contextmanager` and resets the variable in a
  `finally` block, so a raising flow body cannot leak its context into the
  next flow on the same task.
- Nesting is handled by the `ContextVar` token itself: `reset(token)` restores
  the previous value, so no explicit stack is kept. The new `RunContext`
  records the previous one as `parent` for tracing.

## Evidence

`tests/test_context.py::test_isolated_between_tasks` runs two workers under
`asyncio.gather`, each entering its own run and yielding with
`await asyncio.sleep(0)` before asserting. With the `ContextVar`
implementation the test passes. Temporarily replacing the `ContextVar` with a
module-level global makes the test fail: the second worker's `set` overwrites
the first worker's context while it is suspended.

With the global implementation:

```text
===================================================== FAILURES ======================================================
____________________________________________ test_isolated_between_tasks ____________________________________________

    async def test_isolated_between_tasks():
        async def worker(name: str) -> str:
            with _enter_run(name):
                await asyncio.sleep(0)
                ctx = current_run()
                assert ctx is not None
                return ctx.flow_name

>       results = await asyncio.gather(worker("a"), worker("b"))
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_context.py:48:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'b'

    async def worker(name: str) -> str:
        with _enter_run(name):
            await asyncio.sleep(0)
            ctx = current_run()
>           assert ctx is not None
E           assert None is not None

tests/test_context.py:45: AssertionError
============================================== short test summary info ==============================================
FAILED tests/test_context.py::test_isolated_between_tasks - assert None is not None
```

## Consequences

- Tasks called outside any flow see `current_run() is None` and run as plain
  functions. This is intentional: tasks stay unit-testable without a flow.
- `ContextVar` is **not** propagated into `loop.run_in_executor` threads
  automatically. Running tasks in threads or processes (planned for a later
  phase) must copy the context explicitly, e.g. with `contextvars.copy_context()`.
- Any code that calls an async function and stores the coroutine for later
  must enter the run *inside* the coroutine, not around the call that creates
  it, or the context will already be reset by the time the body executes.
  See ADR-002.
