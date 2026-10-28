# tinyorch — Báo cáo review phase 1

Phạm vi: `main` @ `70a1a2f`, tinyorch 0.1.1. Chế độ chỉ-đọc; không file nào trong repo bị thay đổi.
Lệnh đã chạy để xác minh: `uv run pytest` (25 passed, coverage 100 % line + branch), `uv run --isolated --python 3.14 pytest` (25 passed), `uv run basedpyright` (0 lỗi), `uv run ruff check` / `ruff format --check` (sạch), `gh issue/milestone/ruleset/pr/run`, và một probe script chạy các tình huống biên (kết quả được trích làm bằng chứng bên dưới, ký hiệu **[probe]**).

---

## 1. Summary

- **Sức khỏe tổng thể: tốt cho một 0.1.** 230 dòng core, test 100 % line + branch, typing strict xanh trên 3.12/3.13 và cả 3.14. ADR-001 là mẫu ADR đáng giữ (có evidence thực nghiệm).
- **Blocker đáng kể nhất:** hàm generator / async-generator được coi là *sync* (`inspect.iscoroutinefunction` trả `False`), nên `enter_run` mở và đóng **trước khi** thân hàm chạy; `current_run()` trong thân là `None` và `TaskCall` ghi sai. Đây chính là lớp lỗi "context reset before coroutine runs" mà ADR-002 đã né cho coroutine, nhưng còn nguyên cho "tasks that `yield`" — nghĩa là phase 2 không thể bắt đầu từ `@task` hiện tại mà chưa quyết định điều này.
- **Rủi ro lớn nhất cho phase 2:** `RunContext.calls` là `list[TaskCall]` không giới hạn, mỗi item × mỗi stage sinh một `TaskCall` → 10⁶ item × 3 stage = 3 triệu object sống đến hết run, mâu thuẫn trực tiếp với lời hứa "memory stays flat" ở README. Phải tách trace ra khỏi `RunContext` **trước** 0.2, vì đó là thay đổi phá vỡ API.
- **Drift giữa ADR và code:** ADR-002 ghi `functools.update_wrapper`, "partial/bound method không được nhận là coroutine" — cả hai sai so với code và với Python 3.12. Ruleset "PR required" không tồn tại theo API và lịch sử `main` có 5 commit đẩy thẳng.
- **Typing-test không bảo vệ gì:** `reportUnnecessaryTypeIgnoreComment` tắt trong strict, nên hai negative check trong `tests/test_typing.py` sẽ vẫn xanh nếu overload hỏng.

---

## 2. Findings

### 4.1 Correctness và semantics

**F1 — Drift ADR ↔ code.** *Severity: should-fix (docs).*
- ADR-001 dòng 34, 37, 61, 76 vẫn gọi `_enter_run()`; code là `enter_run` (`src/tinyorch/_context.py:44`). Commit `3362746` đã đổi tên, ADR không được cập nhật trong cùng PR — vi phạm chính quy tắc "mỗi quyết định là một ADR trong cùng PR".
- ADR-002 dòng 36–38: "`functools.update_wrapper(self, fn)` được gọi … do đó không dùng `__slots__`". Code copy thủ công 5 thuộc tính (`_task.py:21-25`, `_flow.py:20-24`) và copy thêm `__qualname__` mà ADR không nhắc. Lý do "không `__slots__`" vì thế không còn đúng: copy thủ công hoàn toàn tương thích với `__slots__`. Brief §3 mô tả đúng code; ADR thì không.
- ADR-002 dòng 60–62: "`functools.partial` của async fn và bound method được báo là non-coroutine". **[probe]** trên 3.12.13: `inspect.iscoroutinefunction(partial(afn))` → `True`, bound method async → `True`. Giới hạn thực sự nằm ở chỗ khác (xem F4).
- Các claim còn lại của §3 khớp code: single ContextVar (`_context.py:36`), reset trong `finally`, `except BaseException` (`:49-54`), `parent` (`:45`), bookkeeping trong coroutine (`_task.py:46-58`), hai cast (`:29`, `:67`), eq/hash theo `(module, qualname)` (`:70-81`), Task ngoài flow không ghi (`:34-35`), Flow không ghi `TaskCall` lên parent (`tests/test_flow.py:98-99`), exception re-raise nguyên vẹn.
- *Hướng:* sửa ADR-002 thành "copy thủ công, `__slots__` để mở", đổi mục partial/bound thành danh sách misclassify thật (F4), đổi tên trong ADR-001; thêm một dòng "Superseded-by/Amended" thay vì sửa lặng lẽ để giữ lịch sử.

**F2 — Generator-kind functions: bookkeeping chạy lúc *tạo*, không lúc *chạy*.** *Severity: should-fix ngay, blocker cho thiết kế phase 2.*
- Evidence **[probe]**: `@task def g(x): yield current_run()` gọi trong `@flow` → `next(g)` trả `None`; `@task async def ag(x): yield current_run()` → `await ag.__anext__()` cũng `None`. Nguyên nhân: `_task.py:20` chỉ hỏi `iscoroutinefunction`; generator function rơi vào `_run_sync` (`:32-44`), `self.fn(...)` trả về generator object ngay lập tức, `finally` đặt `ended_at`, `enter_run` của Flow reset ngay sau đó (`_flow.py:31-33`). `TaskCall` ghi `ended_at ≈ started_at`, `error` không bao giờ được ghi dù thân generator ném exception.
- Đây là silent wrong data, cùng lớp với bug mà ADR-001 "Consequences" cảnh báo, nhưng chưa có test hay guard.
- *Hướng:* phase 1 nên **từ chối rõ ràng** (`inspect.isgeneratorfunction` / `isasyncgenfunction` → `TypeError` kèm thông điệp) thay vì âm thầm chạy sai. Việc có hỗ trợ generator-stage hay không là quyết định ADR của phase 2 (xem §4).

**F3 — Context lifecycle.** *Severity: nit hôm nay, should-fix trước phase 2.*
- Exception thường, `KeyboardInterrupt` **[probe]**: reset đúng, `error` được ghi.
- Cancellation **[probe]**: `CancelledError` được ghi vào `RunContext.error` *và* `TaskCall.error`, context reset đúng. Vấn đề là ngữ nghĩa: cancel ≠ fail. Với `TaskGroup` ở phase 2, một item lỗi sẽ cancel toàn bộ sibling, và mọi sibling đều hiện `error=CancelledError`, không phân biệt được với lỗi thật. Cần trường trạng thái (`ok | failed | cancelled`) trong data model.
- `GeneratorExit` ném từ Context khác **[probe]**: đóng một coroutine Flow đang suspended từ `contextvars.copy_context().run(...)` → `_current.reset(token)` (`_context.py:54`) ném `ValueError: <Token> was created in a different Context`, chồng lên `GeneratorExit` và hiện ra dạng "Exception ignored in: <coroutine …>" khi GC. Hôm nay khó gặp (mọi coroutine đều chạy trong asyncio Task cùng context). Phase 2 với pipeline teardown đóng stage coroutine/async generator từ task cha sẽ gặp thường xuyên hơn.
- Child task sống lâu hơn run **[probe]**: `create_task(late())` trong flow, flow return trước → `ctx.calls` vẫn tăng *sau* `ended_at` (0 → 1, `ended_at < calls[-1].ended_at`). Không leak, nhưng "run đã kết thúc" không còn là trạng thái cuối. Structured concurrency (`TaskGroup`) ở phase 2 là câu trả lời; hiện tại nên ghi vào ADR-001 Consequences.
- Double-reset: không xảy ra qua `with`; `@contextmanager` không re-enter được. OK.

**F4 — `is_async` detection và metadata copy.** *Severity: should-fix.*
| Callable | `iscoroutinefunction` | `Task(...)` | Hậu quả |
|---|---|---|---|
| `partial(async_fn)` | `True` | **crash** `AttributeError: 'functools.partial' object has no attribute '__name__'` tại `_task.py:21` | lỗi khó hiểu thay vì thông điệp |
| bound method `async def` | `True` | OK | đúng, trái với ADR-002 |
| object có `async def __call__` | `False` | **crash** `__name__` | — |
| `async def` bọc bởi decorator sync dùng `@wraps` | `False` | OK, `is_async=False` | **misclassify** → trả coroutine chưa await, không ghi gì |
| async generator fn / generator fn | `False` | OK, `is_async=False` | F2 |
| `inspect.markcoroutinefunction(...)` | `True` | OK | — |
- Giới hạn được ghi trong ADR-002 vừa sai vừa thiếu. *Hướng:* (a) hoặc giới hạn `Task` cho `def`/`async def` thật (kiểm `inspect.isfunction`/`ismethod`) và raise `TypeError` rõ, (b) hoặc fallback `getattr(fn, "__name__", type(fn).__name__)`. Tôi khuyên (a): đơn giản, trung thực, đúng tinh thần "core nhỏ"; nới sau nếu dogfooding cần.

**F5 — Identity `(module, qualname)`.** *Severity: should-fix (quyết định), nit về code.*
- **[probe]** Closure factory: `make(1) == make(2)` → `True` (cùng qualname `make.<locals>.inner`). Hai task khác nhau gộp thành một trong set/dict/DAG node.
- **[probe]** `Task(f, name="x") == Task(f, name="y")` → `True`, nhưng `TaskCall.task_name` ghi `name` (`_task.py:61`). Khóa identity và tên ghi nhận tách đôi: checkpoint phase 3 sẽ dùng khóa nào?
- `__main__`: cùng một hàm có `__module__ == "__main__"` khi chạy script và `"pkg.mod"` khi import; với `spawn` ở phase 4, child process re-import entrypoint dưới `__mp_main__` → registry theo `(module, qualname)` (ADR-002 dòng 69–71) sẽ miss.
- *Hướng:* identity = `name` nếu người dùng đặt, ngược lại qualified name; cảnh báo/cấm `<locals>` khi identity được dùng làm khóa bền (phase 3). Quyết định này cần ADR vì nó đổi `__eq__`.

**F6 — Threads.** *Severity: nit (đã ghi trong ADR-001, chưa test).*
- **[probe]** `loop.run_in_executor(None, task)` → `current_run()` là `None`, task chạy *không ghi gì*, không cảnh báo. `asyncio.to_thread(task)` → thấy run và ghi đúng (vì `to_thread` dùng `copy_context()`).
- `ctx.calls.append` từ nhiều thread: append nguyên tử dưới GIL, nhưng mutation `TaskCall` và thứ tự không được đồng bộ; free-threaded build không nằm trong matrix.
- *Hướng:* ghi rõ "`to_thread` được hỗ trợ, `run_in_executor` thì không"; phase 4 bọc submit bằng `copy_context().run`.

### 4.2 API design

**F7 — `Task.__call__ -> R` với R là coroutine.** *Severity: should-fix trước 0.2.*
- Với người dùng, contract hiện tại là *trung thực*: `await fetch(u)` → `bytes`, `fetch(u)` → `CoroutineType[Any, Any, bytes]` (basedpyright 1.40.2 **[probe]**). Hai cast chỉ là nội bộ. Nhưng nó làm `R` mang hai nghĩa: "kết quả" (sync) và "coroutine của kết quả" (async). Mọi API phase 2 có generic trên R đều kẹt: `.map(items) -> list[R]` sẽ là `list[Coroutine]` cho async task; runner phải rẽ nhánh runtime `is_async` thay vì dispatch tĩnh.
- *Khuyến nghị:* giải quyết #2 **trước** `.map()`/pipeline, theo hướng tách `SyncTask[P, R]` / `AsyncTask[P, R]` với base `Task` giữ `isinstance` và overload `task()` trên `Callable[P, Coroutine[Any, Any, R]]` xếp *trước* `Callable[P, R]`. Trade-off: 4 overload thay vì 2, tên lớp lộ trong thông báo lỗi, nhưng `R` thống nhất nghĩa là "kết quả", cả hai cast biến mất, và runner biết tĩnh phải `await` hay không. Phương án "mọi thứ async nội bộ, sync chạy qua `to_thread`" đơn giản hơn nhưng đổi ngữ nghĩa sync task (chạy trong thread, mất thứ tự) — không hợp với "task ngoài flow chạy như hàm thường".

**F8 — `RunContext` đang là ba thứ một lúc.** *Severity: should-fix trước 0.2 (breaking).*
- `_context.py:17-25`: identity (`run_id`, `flow_name`, `parent`) + timing/error + trace (`calls`). Trace không giới hạn là vấn đề (Summary bullet 3). Ngoài ra `error: BaseException` giữ nguyên exception object → giữ traceback → giữ toàn bộ frame locals của run thất bại sống đến khi `RunContext` bị GC; không picklable (phase 3/4).
- *Hướng:* giữ `RunContext` mỏng (identity + timing + counters + status), đưa ghi nhận per-call ra sau một `Recorder` Protocol (`on_start/on_end`), default in-memory list để không phá test và API nhỏ, nhưng với `maxlen`/counter cho pipeline. Đây đồng thời là đường nối cho state store phase 3. ContextVar vẫn chỉ trỏ tới `RunContext`.

**F9 — Những gì sẽ là breaking nếu sửa sau 0.2.**
1. `RunContext.calls` kiểu/ngữ nghĩa (F8).
2. Nghĩa của `R` trong `Task[P, R]` cho async (F7).
3. `TaskCall` thiếu khóa item và status; thêm field có default thì không breaking, nhưng đổi `error` → `status` thì có (F3).
4. `__eq__` bỏ qua `name` (F5).
5. `started_at`/`ended_at` là `time.monotonic` (`_context.py:21,31`): không so sánh được giữa process, không persist được. Phase 3 cần wall-clock. Thêm field thì không breaking; đổi nghĩa thì có — quyết định ngay.
6. `task(fn, name="x")`: runtime chấp nhận (`_api.py:19-21`) nhưng không overload nào khớp **[probe]** `No overloads for "task"`. Chọn một: thêm `name` vào overload 1 hoặc raise.
7. `__version__` nằm trong `__all__` (`__init__.py:17`): bất thường, `from tinyorch import *` kéo theo `__version__`. Nit.

### 4.3 Typing

**F10 — Negative check không bảo vệ overload.** *Severity: should-fix.*
- **[probe]** Thêm `add(1, 2)  # pyright: ignore[reportArgumentType]` (ignore thừa) vào file strict → **không** có diagnostic. `reportUnnecessaryTypeIgnoreComment` tắt trong `strict` của basedpyright. Hệ quả: nếu overload `task()` thoái hóa về `Callable[..., Any]`, `tests/test_typing.py:38-39` vẫn xanh. Positive check (`:28-30, :34`) thì có bảo vệ.
- *Hướng:* bật `reportUnnecessaryTypeIgnoreComment = "error"` trong `[tool.basedpyright]`; cân nhắc `reportIgnoreCommentWithoutRule`.

**F11 — Thiếu case.** *Severity: nit.*
- Chưa có: `@flow(name=...)` async với `assert_type`; `assert_type(fetch("u"), CoroutineType[Any, Any, bytes])` (lưu ý pyright 1.1.414 suy ra `CoroutineType`, không phải `Coroutine` — `assert_type` với `Coroutine` sẽ fail **[probe]**); keyword-only (**[probe]** `kwonly(1, 2.0)` bị bắt đúng); `*args/**kwargs`; `Concatenate` (compile sạch); negative `@task(name=1)`; `task(raw, name="x")` (F9.6).
- Hai cast là tối thiểu *với thiết kế một lớp*; `object` đã dùng đúng chỗ (`_run_async -> object`, `Awaitable[object]`). Tách lớp xóa cả hai.
- `[[tool.basedpyright.executionEnvironments]] root = "tests"` (`pyproject.toml:42-43`) không có comment giải thích; nếu để tests import như top-level, ghi lại.

### 4.4 Tests

**F12 — Coverage gate trong `addopts` làm mọi lần chạy một phần đều đỏ.** *Severity: should-fix (DX).*
- `pyproject.toml:48` gắn `--cov-fail-under=95` vào mọi invocation. **[probe]** `uv run pytest tests/test_api.py` → 6 passed nhưng `FAIL Required test coverage of 95% not reached (83.77 %)`. Người dùng VS Code (`python.testing.pytestArgs: ["tests"]`) cũng bị khi chạy một test.
- *Hướng:* chuyển `--cov*` sang lệnh trong CI (`uv run pytest --cov ...`) hoặc giữ `addopts` nhưng bỏ `--cov-fail-under` và đặt `fail_under` trong `[tool.coverage.report]` chỉ cho `coverage report`.

**F13 — Test tautological / test fixture.** *Severity: nit.*
- `tests/test_api.py:30-33` `test_task_keeps_fn`: `task(raw).fn is raw` — gần như là test constructor của dataclass.
- `tests/test_flow.py:42-46, 60-66`: số calls được *tính trong fixture* (`_pipeline` trả `len(ctx.calls)`), test chỉ so với 3; không kiểm `task_name`, thứ tự, hay `error`.
- `tests/test_flow.py:98-99` `test_nested_flow` kiểm `("_outer", 0)`: chứng minh Flow không ghi lên parent (tốt) nhưng không chứng minh run con *có* ghi `add`.
- `tests/test_task.py:68`: `ended_at - started_at >= 0.01` với `sleep(0.01)` — đúng nhờ monotonic, nhưng là timing assertion; đủ dùng, nên ghi chú.

**F14 — Hành vi §3 chưa có test.**
- Nhánh `except BaseException` với non-`Exception` (`KeyboardInterrupt`, `CancelledError`) ở cả `enter_run` và `Task` — 100 % branch coverage vẫn không chạm vì `ValueError` là `Exception`.
- Async task gọi mà không `await` → không ghi gì (**[probe]** đúng, chưa test).
- `__qualname__`, `__module__` được copy (`test_task_metadata` chỉ kiểm `__name__`, `__wrapped__`, `__doc__`).
- `__eq__` bỏ qua `name` (hành vi không được ghi ở đâu).
- Claim partial/bound method của ADR-002 (sai, và không test).
- ADR-001 Consequences: `run_in_executor` không propagate; `create_task` con *kế thừa* run cha (test gather hiện tại chỉ kiểm *cô lập*, không kiểm *kế thừa*).
- `__all__` khớp tập public name; `__version__` resolve.
- F2: generator function trong flow.

### 4.5 Tooling, packaging, process

**F15 — `pyproject.toml`.** *Severity: nit.*
- Classifiers (`:10-16`) thiếu `Programming Language :: Python :: 3.14` (3.14 là stable hiện hành; test pass trên 3.14.4 **[probe]**), `Operating System :: OS Independent`, `Framework :: AsyncIO`, `Intended Audience :: Developers`, `Topic :: …`. PEP 639 `license`/`license-files` đúng, bỏ classifier License là đúng.
- `[project.urls]` thiếu `Changelog`/`Documentation` (ADR dir là docs duy nhất).
- `exclude_also` `"\\.\\.\\."` loại mọi dòng chứa `...` (kể cả `Ellipsis` dùng thật). Chấp nhận được, nên ghi chú.

**F16 — CI gate chưa đủ.** *Severity: should-fix.*
- `ci.yml:13` matrix 3.12/3.13, thiếu 3.14 (và 3.15 khi ra).
- Không có `uv lock --check`: `--frozen` dùng lock cũ lặng lẽ nếu `pyproject` đổi dependency mà quên lock.
- Không có kiểm tra README render / link tuyệt đối — 0.1.1 là release chỉ để sửa đúng lỗi này (`71dbafd`). Gate thiếu chính là gate đã cháy.
- `publish.yml:16-17`: không kiểm `tag == project.version`; tag `v0.2.0` với `pyproject` 0.1.1 chỉ fail ở bước upload PyPI (hoặc tệ hơn, publish nhầm version). *Hướng:* một step so `uv version --short` với `${GITHUB_REF_NAME#v}`; và một job `uv build` + `twine check`/`uv publish --check-url` trong CI thường.
- Có thể đỏ vì lý do phi-code: `uv python install` (network), `--cov-fail-under` khi thêm code trước test (chủ ý), `setup-uv@v5` pin major.

**F17 — Process claim ≠ lịch sử.** *Severity: should-fix (process).*
- `gh api repos/murilegus/tinyorch/rulesets` → `[]`; `rules/branches/main` → rỗng. Repo cho phép merge commit *và* rebase merge (`gh repo view`), trái với "squash merges".
- Lịch sử `main`: `70a1a2f`, `6c350c6`, `1590350`, `0d3b6b9`, `a22ce58` không qua PR (không có `(#N)`, run CI là `push` trực tiếp). Commit mới nhất hôm nay là một trong số đó.
- Squash message: PR #4 (`3362746`) có body mang cả 5 commit trung gian (`fix: correct initialization of task name`, `refactor: rename _enter_run…`) — ồn nhưng còn thông tin; PR #5 (`164636e`) body rỗng dù là PR đưa public API ra; #6 là hai bullet.
- Đáng lẽ là issue: đổi tên `_enter_run`→`enter_run` (quyết định naming, chỉ nằm trong commit body); thêm coverage floor 95 % (quyết định process); bảng so sánh README (claim không có nguồn, xem F19).
- Milestone "Phase 1 — core API" có 0 issue: phase 1 không được track bằng issue như §2 mô tả.
- *Hướng:* tạo ruleset thật (PR + CI required, squash only, no force push, không bypass cho admin), và chấp nhận rằng 5 commit kia là bằng chứng ruleset chưa từng có.

**F18 — Repo hygiene.** *Severity: nit.*
- `.vscode/settings.json` đặt Pylance `typeCheckingMode: "standard"` trong khi CI là basedpyright `strict` + `failOnWarnings` → editor báo ít lỗi hơn CI. `extensions.json` khuyên Pylance, không có `detachhead.basedpyright`. Hoặc đồng bộ, hoặc đừng commit `.vscode/`.
- Badges, link tuyệt đối: OK sau 0.1.1. README `:10` "phase 2 in progress" khớp milestone 4 (1 issue mở, #2).
- ADR status line: ADR-001 "accepted", ADR-002 "accepted (implemented in 0.1.0)" — đúng về trạng thái, sai về nội dung (F1).

### 4.6 Documentation

**F19 — Bảng ba trục README (`README.md:62-69`).** *Severity: should-fix (uy tín).*
Tác giả chưa dùng Prefect; các claim dưới đây theo hiểu biết của tôi về Prefect 3 / Dagster / Bytewax và cần được xác minh bằng benchmark trước khi giữ nguyên:
- "Execution: one stage finishes before the next starts" — **không đúng tuyệt đối với Prefect**: `task.submit()`/`task.map()` trả future, task hạ nguồn nhận future và bắt đầu khi future resolve (task runner mặc định chạy thread pool). Đúng với Airflow dynamic task mapping (XCom materialize). Nên viết "scheduling theo task, kết quả materialize giữa task; không có backpressure" — đó mới là điểm khác biệt thật.
- "Infra: server + database" — Prefect 3 chạy local với ephemeral API + SQLite, `dagster dev` cũng vậy; claim đúng cho production, không đúng cho "chạy thử". Ghi "server + DB (local SQLite được)".
- "Shared resources: per process, awkward" — **sai với Dagster**: Resources là first-class, có lifecycle (context-manager resources), inject qua tham số. Với Prefect là blocks, không có lifecycle — "awkward" tạm chấp nhận.
- "Stream processors: cluster / unbounded" — Bytewax chạy một process; Flink có batch execution mode cho bounded input. Faust gần như không còn maintain (fork `faust-streaming`). Nên bỏ Faust hoặc chú thích.
- Cột tinyorch: "pipelined, bounded buffers", "per item" resume, "first-class" resources mô tả **phase 2–4**, nhưng bảng không đánh dấu là planned; người đọc PyPI 0.1.1 sẽ thấy không khớp. Thêm "(0.2+)" / "(planned)" vào ô.
- **Benchmark Prefect 10k item nên đo:** kịch bản chung — 10 000 URL → `fetch` (async, latency giả 50 ms, 5 % lỗi ngẫu nhiên có seed) → `parse` (CPU nhẹ) → `write`. Ba triển khai: bare `asyncio` + `Semaphore` (sàn overhead), Prefect (`.map()` với thread-pool runner, và `.submit()` trong vòng lặp), tinyorch 0.2. Số đo: (1) wall-clock ở concurrency 1/16/64; (2) peak RSS (`resource.getrusage`) — đây là số chứng minh "memory flat"; (3) time-to-first-output — số chứng minh "pipelined"; (4) overhead orchestration/item = (wall − tổng latency giả / concurrency) / N; (5) kill ở 50 % rồi resume: số `fetch` bị làm lại — số chứng minh "per item"; (6) cold start (Prefect server/DB); (7) LOC. Công bố script trong `benchmarks/` để claim có nguồn.

**F20 — ADR.** *Severity: should-fix (docs).*
- ADR-001: "why" đọc 2 phút được, Evidence là phần giá trị nhất. ADR-002: trộn quyết định với chi tiết đã stale; người lạ sẽ tin `update_wrapper` và partial-limitation.
- Quyết định trong code chưa có ADR: (1) `run_id = uuid4().hex[:12]` (48 bit; đủ cho in-memory, nhưng phase 3 dùng làm khóa bền?); (2) `time.monotonic` cho timestamp; (3) `error` giữ exception object (giữ traceback/frames); (4) `__eq__` bỏ `name`; (5) `TaskCall` không ghi args/item/result; (6) cancel = error; (7) `__version__` qua `importlib.metadata` (fail nếu chạy từ source không install); (8) coverage floor 95 %, ruff `ALL` + ignore list; (9) `current_run` public nhưng `enter_run` không — tức người dùng *đọc* được run nhưng không *mở* được run ngoài `Flow`.

---

## 3. Decisions to make before 0.2

| # | Quyết định | Lựa chọn | Khuyến nghị | ADR |
|---|---|---|---|---|
| 1 | Nghĩa của `R` cho async task (#2) | (a) giữ một lớp + cast; (b) `SyncTask`/`AsyncTask` + overload; (c) mọi thứ async nội bộ | **(b)** — `R` = kết quả, runner dispatch tĩnh, xóa cast; (c) đổi ngữ nghĩa sync task | ADR-002 amend → ADR-004 |
| 2 | Trace per-call ở đâu | (a) `calls` list như nay; (b) `Recorder` Protocol, `RunContext` mỏng; (c) chỉ counters | **(b)** với default in-memory có `maxlen`; (a) không flat memory; (c) mất debuggability | ADR-005 |
| 3 | Generator / async-generator function | (a) `TypeError`; (b) hỗ trợ như stage; (c) im lặng như nay | **(a)** ngay ở 0.1.2; (b) là ADR-003 phase 2 quyết | ADR-002 amend, ADR-003 |
| 4 | Identity của Task | (a) `(module, qualname)`; (b) `name` nếu đặt, else qualified name; (c) object identity | **(b)**, cấm `<locals>` khi làm khóa bền | ADR-002 amend |
| 5 | Cancel có phải error? | (a) `error=CancelledError`; (b) `status` enum + `error` | **(b)** — TaskGroup sẽ cancel hàng loạt | ADR-005 |
| 6 | Timestamp | (a) monotonic; (b) wall-clock; (c) cả hai | **(c)**: monotonic cho duration, `time.time()` cho persist | ADR-005 |
| 7 | `task(fn, name=)` | (a) thêm vào overload 1; (b) raise | **(a)** — rẻ, đã chạy được | — |
| 8 | DAG tĩnh trong phase 2 | (a) DAG + runner; (b) pipeline tuyến tính, DAG = topology stage sau | **(b)** (xem §4) | ADR-003 |
| 9 | Ruleset `main` | tạo thật, squash-only | làm ngay | — |

---

## 4. Phase 2 plan

### Câu hỏi mở: pipelining trước DAG? DAG tĩnh còn chỗ đứng?

**Pipelining trước, và DAG tĩnh như một *scheduler* không có chỗ đứng.** Lý do:
- Positioning là "item-level": đơn vị lập lịch là *item*, không phải *task*. DAG kiểu Prefect/Airflow lập lịch *task* theo phụ thuộc dữ liệu giữa task; nó không nói gì về backpressure, buffer, hay memory theo N item. README `:71-75` hứa đúng những thứ DAG không cho.
- Trong crawl + LLM pipeline, topology gần như luôn là chuỗi tuyến tính, thỉnh thoảng fan-out (một trang → nhiều link) và hiếm khi fan-in. Thứ "DAG" duy nhất cần là **topology của stage** — và nó đã được biểu diễn bằng cách nối stage; không cần `depends_on`, không cần topological sort, không cần scheduler.
- Nếu sau này cần nhánh (A → B, A → C), thêm `fan_out`/`tee` stage là đủ. Để điều đó cho khi dogfooding (phase 5) *đòi*, chứ không thiết kế trước.

### Ba candidate API

**A. Prefect-style `.map()`**
```python
@flow
async def crawl(urls: list[str]) -> list[Doc]:
    htmls = await fetch.map(urls, concurrency=16)  # list[str]
    docs = await parse.map(htmls)  # list[Doc]
    await store.map(docs, concurrency=4)
    return docs
```
- Cơ chế: `TaskGroup` + `Semaphore`; `create_task` copy contextvars nên mỗi lần `fetch` thấy run cha.
- Tương tác #2: `.map` trên `AsyncTask` trả `Awaitable[list[R]]`, trên `SyncTask` trả `list[R]` — bắt buộc tách lớp, nếu không kiểu trả về là `list[Coroutine]`.
- Điểm yếu: `htmls` materialize toàn bộ giữa stage → *đúng cái README nói là sai*; không backpressure; không time-to-first-output. Chỉ là sugar cho `gather`.

**B. Stage chaining bằng async iterator**
```python
pipe = source(urls) | fetch.stage(workers=16, buffer=64) | parse.stage() | store.stage(workers=4)
async for doc in pipe:  # hoặc: await pipe.drain()
    ...
```
- Cơ chế: mỗi stage là async generator đọc từ `asyncio.Queue(maxsize=buffer)` của stage trước, `TaskGroup` cho worker, `aclose()`/cancellation lan ngược khi consumer dừng; contextvars propagate vì worker task được tạo *trong* run.
- Tương tác #2: cần biết sync/async để chạy inline hay `to_thread`; ngoài ra nếu cho phép thân stage là async generator thì cần lớp thứ ba/thứ tư — F2 cho thấy đây là nơi dễ sai nhất.
- Điểm yếu: `|` là cú pháp đẹp nhưng topology ẩn trong object chain, khó inspect; async-generator teardown là mảnh đất của `GeneratorExit` từ context khác (F3).

**C. `Pipeline` object tường minh**
```python
pipe = Pipeline(source=urls, buffer=64)
pipe.stage(fetch, workers=16)
pipe.stage(parse)
pipe.stage(store, workers=4, on_error="skip")


@flow
async def crawl() -> Stats:
    return await pipe.run()  # Stats: per-stage ok/failed/cancelled counts
```
- Cơ chế: như B (queue + TaskGroup + Semaphore), nhưng topology là *dữ liệu* (`list[Stage]`), stage body là `@task` thường `item -> result` (hoặc `item -> Iterable[result]` cho fan-out); source là iterable/async iterable, không phải task.
- Tương tác #2: `Stage` giữ `SyncTask | AsyncTask`, dispatch tĩnh; không cần generator-kind task.
- Điểm yếu: nhiều dòng hơn B; `Pipeline` là object mới trong public surface.

### Khuyến nghị: **C**, với engine của B, giữ A ra ngoài.
- C làm topology inspectable → phase 3 gắn checkpoint vào *ranh giới stage*, phase 4 gắn resource vào *lifecycle stage* (start/stop worker), phase 5 CLI in topology. B cho cùng engine nhưng giấu những thứ đó trong chain.
- Người dùng chỉ viết `@task` một-item-một-kết-quả — cùng hàm unit-test được ngoài flow (giữ consequence của ADR-001). Async generator chỉ được chấp nhận làm *source*, không làm stage body: tránh toàn bộ lớp lỗi F2/F3.
- `.map()` có thể thêm sau như sugar `Pipeline([stage]).run()` nếu dogfooding cần; không nên là primitive.

ADR cần: **ADR-003** mô hình pipelining (envelope item, stage, bounded queue, backpressure, sentinel, error policy, ordering không bảo đảm); **ADR-004** tách Sync/Async task (#2); **ADR-005** run records (recorder, status, timestamp) — ba quyết định độc lập, ba ADR, mỗi cái cùng PR với code.

### Milestones (PR-sized)

| # | PR | Test phải thêm | Bẫy dễ dính |
|---|---|---|---|
| 1 | `SyncTask`/`AsyncTask` + reject generator/partial (#2, quyết định 1, 3) | `assert_type(fetch("u"), CoroutineType[...])`; `assert_type(await fetch("u"), bytes)`; `TypeError` cho generator fn; `isinstance(x, Task)` vẫn true | Thứ tự overload: `Callable[P, Coroutine[Any, Any, R]]` phải đứng trước `Callable[P, R]`; pyright suy ra `CoroutineType` chứ không phải `Coroutine` |
| 2 | `Recorder` Protocol, `RunContext` mỏng, `status`, wall-clock (quyết định 2, 5, 6) | recorder `maxlen` không tăng memory (đo bằng `len`); counters đúng; cancel → `cancelled` không phải `failed` | Giữ `RunContext.calls` tương thích ngược một release (deprecated property) hay cắt luôn — quyết định ghi vào ADR-005 |
| 3 | `_Envelope(key, value, attempt)` + `Stage` + `Pipeline` tuần tự qua `asyncio.Queue(maxsize)`, `workers=1` | thứ tự giữ nguyên; producer *block* khi buffer đầy (consumer chậm, assert `qsize()`); `current_run()` thấy trong stage body (regression F2); sentinel đóng từng stage | `asyncio.Queue()` mặc định **không giới hạn** (`maxsize=0`); sentinel với N worker phải gửi N lần hoặc đếm |
| 4 | `workers=n`: `TaskGroup` + `Semaphore` | max in-flight ≤ n (đếm bằng counter trong task giả); contextvars vào worker; kết quả đủ | Worker phải được `create_task` *bên trong* run (context copy lúc tạo); `TaskGroup` cancel toàn bộ sibling khi một worker ném → item đang bay mất |
| 5 | Error policy per item (`raise` / `skip` + ghi failed) và shutdown sạch | một item lỗi không giết run với `skip`; với `raise`: run kết thúc, context reset, không "Task was destroyed but it is pending" (`-W error`); source async generator được `aclose()` | Producer kẹt ở `put()` mãi khi consumer đã chết → deadlock lúc shutdown; phải cancel producer hoặc drain |
| 6 | Sync task trong pipeline: inline (mặc định) hoặc `to_thread` | `to_thread` thấy run (probe đã xác nhận); `run_in_executor` ghi nhận là không hỗ trợ | Thread pool mặc định `min(32, cpu+4)`: `workers` lớn hơn pool sẽ âm thầm tuần tự hóa |
| 7 | Fan-out stage (`item -> Iterable[item]`) + `Stats` per stage | counts đúng; key con `(parent_key, i)` | Fan-out phá 1:1 ordering và identity → đây là hook cho phase 3, đừng sinh key bằng `id()` |
| 8 | Docs + CI: ADR-003/004/005, README đánh dấu planned → done, `examples/crawl.py`, matrix 3.14, `uv lock --check`, README render check, tag==version check | — | README là thứ đã làm cháy release một lần |

### Phase 1 phải đổi gì
- **Breaking:** `Task[P, R]` nghĩa của `R` (PR 1); `RunContext.calls` (PR 2); `TaskCall` thêm `status`/`key` (PR 2/3); `__eq__` theo `name` (quyết định 4).
- **Không breaking:** reject generator/partial với `TypeError` (trước đó là hành vi sai); thêm `started_wall`; thêm `Pipeline`, `Stage`, `Recorder` vào `__all__`.
- **Không đổi:** `enter_run`/ContextVar (ADR-001 đứng vững; TaskGroup chỉ làm nó mạnh hơn); `@task`/`@flow` cú pháp.

### Non-goals phase 2
DAG scheduler / nhánh tùy ý; retry/timeout per item (envelope có `attempt` để phase 3 làm); persistence/checkpoint; resources; process workers; CLI; bảo đảm thứ tự output qua stage concurrent; rate limiting; priority queue; chèn stage lúc chạy; hỗ trợ `anyio`/trio.

---

## 5. Phases 3–5 outlook

**Phase 3 — checkpoint per item, resumable run, state store.** Rủi ro chính là *identity của item*: resume chỉ có nghĩa nếu cùng một item ở lần chạy sau có cùng khóa, mà input là `list[str]`/iterable không có khóa tự nhiên; fan-out càng làm khó (khóa con phụ thuộc thứ tự). Phase 2 phải để chỗ: `_Envelope.key` do source/`key=` callable quyết định ngay từ PR 3 (mặc định hash ổn định của value, không phải `id()`), khóa stage = identity Task (quyết định 4) nên `<locals>` và `__main__` phải bị chặn ở đó, `Recorder` là Protocol để `SqliteRecorder` cắm vào mà không đổi `RunContext`, timestamp wall-clock, và `error` phải lưu được dạng string/type chứ không phải exception object. Câu hỏi thiết kế cần trả lời sớm: checkpoint ở *đầu vào* stage (at-least-once, cần idempotent) hay *đầu ra* (exactly-once trong process, mất khi crash giữa chừng) — README hứa "a rerun only does what is left", tức at-least-once là đủ, nhưng ADR phải nói rõ.

**Phase 4 — resources với lifecycle và injection; process workers.** Rủi ro chính là *scope*: một browser/LLM client sống theo run, theo stage, hay theo worker? Injection qua tham số (kiểu Dagster) va với `ParamSpec`: tham số được inject phải biến mất khỏi chữ ký public — đây là chỗ `Concatenate` hoặc một `Depends`-marker vào cuộc, và là lý do giữ `Concatenate` trong typing test từ phase 2. Process worker đòi picklability: `Task` không pickle được (ADR-002 đã ghi), nên phase 2 phải không để bất kỳ closure/lambda nào lọt vào `Stage`/`Pipeline` state, và registry theo identity ổn định (quyết định 4) phải sẵn sàng; contextvars không qua được process → `RunContext` tối thiểu (`run_id`, `flow_name`) phải serializable để tái tạo bên worker.

**Phase 5 — dogfooding + CLI.** Rủi ro chính là phát hiện rằng pipeline thật cần thứ phase 2 không có (rate limit per host, retry với backoff, dedup URL) và bị cám dỗ nhét vào core. Giữ kỷ luật "adapter sau Protocol": phase 2 nên để `Stage` nhận một `middleware`/hook điểm duy nhất (trước/sau mỗi item) thay vì option mới cho mỗi nhu cầu; CLI chỉ cần `Pipeline` là dữ liệu inspect được (lý do chọn C) và `Recorder` để in tiến độ. Benchmark Prefect (F19) nên làm *trong* phase này, với pipeline thật, để bảng README có nguồn.

---

## 6. Questions for the author

1. Ruleset trên `main` có thật không? API trả rỗng và 5 commit vào `main` không qua PR — hay đó là bypass của admin?
2. `enter_run` cố ý không public? Người dùng muốn test một task *trong* run mà không viết `Flow` thì làm thế nào — đây là nhu cầu thật khi viết test cho phase 2.
3. Cancel có nên được coi là lỗi của run? Câu trả lời đổi data model (quyết định 5).
4. `name=` trên task là tên hiển thị hay là identity? Hiện là hiển thị; checkpoint phase 3 sẽ cần một trong hai làm khóa.
5. Có chấp nhận cắt tương thích `RunContext.calls` ngay ở 0.2 (alpha) hay cần một release deprecate?
6. Mục tiêu "core ~2k dòng": tính cả `Pipeline`/`Recorder` hay chỉ `task`/`flow`/`context`? Plan trên ước lượng core sau phase 2 ở ~700–900 dòng.
7. Dogfooding crawl + LLM: tỉ lệ sync/async task thực tế ra sao? Nếu gần như toàn async, PR 6 (sync trong pipeline) có thể lùi.
8. Bảng README: có muốn tôi coi "chưa benchmark" là lý do đánh dấu *tất cả* ô so sánh Prefect là "theo tài liệu, chưa đo" cho đến khi có `benchmarks/`?
