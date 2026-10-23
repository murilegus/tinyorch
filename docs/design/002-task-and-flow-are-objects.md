# ADR-002: `@task` and `@flow` return objects, not wrapped functions

- Status: accepted (implementation lands in `feat/task` and `feat/flow`)
- Date: 2026-10-24
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

- `functools.update_wrapper(self, fn)` is called in `__init__` so
  `__doc__`, `__name__`, `__module__` and `__wrapped__` are preserved. As a
  consequence `Task` and `Flow` do **not** use `__slots__`.
- A `Task` called outside a flow runs its function directly and records
  nothing; inside a flow it appends a `TaskCall` to the current
  `RunContext`. Exceptions are re-raised unchanged to keep the user's
  tracebacks and `except SomeError` clauses intact.
- Async functions are detected with `inspect.iscoroutinefunction`. For an
  async function, `__call__` returns a coroutine defined by tinyorch that
  wraps `await fn(...)`; all bookkeeping (entering the run, recording the
  call) happens *inside* that coroutine. Doing it in `__call__` would run
  before the user's body executes and reset the context too early (see
  ADR-001). The return type of `__call__` for the async case is reconciled
  with a single `typing.cast`; a later phase may replace it with overloads.
- `TaskCall` is a mutable dataclass: it is created when the task starts and
  updated with `ended_at` / `error` when it finishes. No consumer currently
  needs immutability; if persistence requires it, switch to
  `frozen=True` plus `dataclasses.replace`.

## Consequences

- `isinstance(fetch, Task)` is true and `fetch.name`, `fetch.is_async` are
  public. Users who need the raw function use `fetch.fn` or `fetch.__wrapped__`.
- `functools.partial` of an async function and bound methods are reported as
  non-coroutine by `inspect.iscoroutinefunction`; such callables are treated
  as sync. Documented as a known limitation for this phase.
- Pickling `Task` instances is not supported yet; moving tasks to worker
  processes will require a registry keyed by the same `(module, qualname)`
  identity rather than pickling the object.
