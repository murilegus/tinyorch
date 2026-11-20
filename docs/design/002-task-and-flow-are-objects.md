# ADR-002: `@task` and `@flow` return objects, not wrapped functions

- Status: accepted (implemented in 0.1.0)
- Date: 2026-10-24
- Amended: 2026-11-20 — corrected two statements that did not match the code
  (metadata copying, `partial` / bound-method detection) and recorded the
  rule for which callables are accepted (0.1.2)
- Scope: `tinyorch._task`, `tinyorch._flow`, public decorators

## Context

The decorators are the whole public API. Later phases need to hang behaviour
on a decorated callable: `.map()`, `.submit()`, `.with_options(retries=3)`,
identity for DAG edges, and a stable name for checkpoints. The shape chosen
now must survive those additions without breaking user code.

## Options considered

1. **Closure wrapper with `functools.wraps`.**
   Returns a plain function. Extra behaviour must be attached as attributes
   on the function object, which type checkers cannot see and which
   `functools.wraps` may clobber when copying `__dict__`. Equality and
   hashing fall back to the closure's identity.
2. **Class instance (`Task[P, R]`, `Flow[P, R]`) with `__call__`.**
   Methods live on the class and are fully typed. `ParamSpec` (`**P`) and a
   return `TypeVar` (`R`) preserve the wrapped signature through `__call__`.
   `__eq__`/`__hash__` can be defined on `(fn.__module__, fn.__qualname__)`,
   giving tasks a stable identity for sets, dicts and DAG nodes.

## Decision

Option 2. `task()` and `flow()` are decorator factories that return `Task`
and `Flow` instances. Both support `@task` and `@task(name=...)` via two
`@overload`s; the wrapped function is positional-only so the two forms
cannot be confused.

Details fixed by this decision:

- `__name__`, `__qualname__`, `__module__`, `__doc__` and `__wrapped__` are
  copied onto the instance explicitly in `__init__`, not with
  `functools.update_wrapper`, so that each attribute is declared and typed.
  `Task` and `Flow` do not use `__slots__` today; nothing in this decision
  depends on that, and it is left open.
- Only functions defined with `def` / `async def` and bound methods are
  accepted (`inspect.isfunction` or `inspect.ismethod`). Anything else —
  `functools.partial`, an instance with `__call__`, a builtin — raises
  `TypeError` at decoration time. These objects have no reliable
  `__name__` / `__qualname__`, which identity and bookkeeping depend on.
- Generator and async-generator functions raise `TypeError` at decoration
  time. Calling one only *creates* the generator; the body runs later, when
  it is iterated, after the bookkeeping has already closed. The recorded
  call would end immediately and `current_run()` inside the body would be
  `None` — the same failure as entering the run outside the coroutine
  (ADR-001), but silent. Whether a stage may `yield` is a phase 2 decision.
- A `Task` called outside a flow runs its function directly and records
  nothing; inside a flow it appends a `TaskCall` to the current
  `RunContext`. Exceptions are re-raised unchanged to keep the user's
  tracebacks and `except SomeError` clauses intact.
- Async functions are detected with `inspect.iscoroutinefunction`. For an
  async function, `__call__` returns a coroutine defined by tinyorch that
  wraps `await fn(...)`; all bookkeeping (entering the run, recording the
  call) happens *inside* that coroutine. Doing it in `__call__` would run
  before the user's body executes and reset the context too early (see
  ADR-001). Typing of the async case requires two `cast`s: one on the
  wrapped coroutine (`Awaitable[object]`) and one on the coroutine returned
  to the caller (`R`). See Consequences.
- `TaskCall` is a mutable dataclass: it is created when the task starts and
  updated with `ended_at` / `error` when it finishes. No consumer currently
  needs immutability; if persistence requires it, switch to
  `frozen=True` plus `dataclasses.replace`.

## Consequences

- `isinstance(fetch, Task)` is true and `fetch.name`, `fetch.is_async` are
  public. Users who need the raw function use `fetch.fn` or `fetch.__wrapped__`.
- Bound methods are classified correctly: `inspect.iscoroutinefunction`
  returns `True` for a bound `async def` method. (An earlier version of this
  ADR said the opposite; that was wrong for Python 3.12.)
- Known limitation: an `async def` wrapped by a *synchronous* decorator that
  uses `functools.wraps` is a plain function to `inspect`, so it is treated
  as sync. Calling it returns an un-awaited coroutine and the recorded call
  ends at once. Decorate with `@task` innermost, or make the wrapper
  `async def`.
- `Task.__call__` needs two `cast`s because a single `Task[P, R]` cannot
  express "R is a coroutine when fn is async". Candidate fix: split into
  `SyncTask[P, R]` and `AsyncTask[P, R]` with `@overload`s on `task()`, so
  `await fetch(...)` types without casts. Deferred until the runner
  (phase 2) shows whether it needs to distinguish the two anyway.
  Tracked in [#2](https://github.com/murilegus/tinyorch/issues/2).
- Pickling `Task` instances is not supported yet; moving tasks to worker
  processes will require a registry keyed by the same `(module, qualname)`
  identity rather than pickling the object.
- `ParamSpec` preserves parameter names, so `Task[[int, int], int]` is not
  equal to the type inferred for `def add(a: int, b: int)`. Typing tests
  therefore assert at call sites (`assert_type(add(1, 2), int)`) and use
  `# pyright: ignore[...]` negative checks, not `assert_type` on the object.
- Members of package-private modules (`_context.enter_run`) carry no second
  underscore; the module name already marks them internal. Public API is
  whatever `tinyorch.__all__` exports.
- `RunContext` records `ended_at` and `error`, set by `enter_run()` on exit,
  so `Flow` needs no try/except of its own.
