# `.claude/` — Claude Code hooks & guardrails

This directory configures how Claude Code behaves in this repo. The headline
feature is a set of **architecture guardrails**: hooks that mechanically enforce
the rules in [`CLAUDE.md`](../CLAUDE.md) so they can't be violated by accident,
instead of relying on the model to remember them.

Everything is wired through [`settings.json`](./settings.json). Validation
scripts live in [`scripts/`](./scripts/); the older doc-automation hooks live in
[`hooks/`](./hooks/). In each directory the underscore-prefixed file
(`scripts/_hook_paths.py`, `hooks/_repo.sh`) is shared plumbing rather than a
check — both resolve the repo root so no hook depends on the session's cwd.

---

## How hooks work here

Claude Code runs a hook **command** at a lifecycle event, matched against the
tool being used. Each hook receives the tool-call payload as JSON on **stdin**
(`tool_name`, `tool_input.file_path`, `tool_input.content` / `.new_string` /
`.command`, …) and signals via its **exit code**:

| Event | When | Exit 2 means |
|---|---|---|
| `PreToolUse` | before the tool runs | **block the tool call** (it never executes) |
| `PostToolUse` | after the tool ran | tool already ran; **stderr is fed back to Claude** to fix |
| `SessionStart` | session start | (advisory; stdout becomes context) |
| `Stop` | end of a turn | **block the turn from ending**; stderr is fed back to Claude to fix |

For our validators, **exit 0 = allow, exit 2 = violation** (the stderr message
explains what and how to fix). Anything printed to stderr on a non-zero exit is
shown to Claude.

### Why some checks are PreToolUse and others PostToolUse

- **Import / command checks are `PreToolUse`.** They only need the incoming text
  (`content`, `new_string`, or `command`) and are best blocked *before* the
  write happens. A line-anchored regex on a fragment is reliable.
- **Whole-file AST checks are `PostToolUse`.** Syntax-, ORM-write-, and
  audit-checks need to parse the *resulting* file. An `Edit` only gives you the
  replaced fragment, which often won't parse on its own, so these read the
  finished file from disk after the write. They can't *prevent* the write, but
  exit 2 surfaces the problem immediately so the next action is a fix.

### Hooks must never depend on the working directory

Claude Code spawns every hook with the **session's shell cwd** — whatever
directory the last Bash tool call `cd`'d into, not the repo root. A hook that
resolves anything relative to cwd therefore breaks as soon as the session moves
into a subdirectory, and it breaks *loudly in the wrong direction*: a
`PreToolUse` script that can't be found exits non-zero, which the harness reads
as **blocked**, so a single stray `cd` stops every `Write`, `Edit`, and `Bash`
call in the session. The `Stop`/`PostToolUse` variants fail the other way —
`git rev-parse --show-toplevel` returns nothing, the hook `exit 0`s, and the
check silently stops running while still looking green.

Two rules, both mechanically enforced by
[`tests/test_hook_cwd_independence.py`](../tests/test_hook_cwd_independence.py):

1. **`settings.json` invokes hooks through `$CLAUDE_PROJECT_DIR`**, never a
   relative path:
   `python3 "${CLAUDE_PROJECT_DIR:-.}/.claude/scripts/check_foo.py"`.
   Claude Code sets that variable to the session's project root for every hook
   it spawns; the `:-.` fallback keeps the old behaviour under any other runner.
2. **Each script anchors its own cwd before touching a path.** Python scripts
   call `anchor()` from [`scripts/_hook_paths.py`](./scripts/_hook_paths.py);
   shell hooks `source "$( dirname "${BASH_SOURCE[0]}" )/_repo.sh"`, which sets
   `$REPO` and `cd`s there. Both resolve the root from `$CLAUDE_PROJECT_DIR`,
   falling back to the hook file's **own location** (`<root>/.claude/…`) — so
   they work even when the variable is unset. `git rev-parse` and cwd are
   last-resort guesses, never the primary source.

Anchoring cwd rather than rewriting every path is deliberate: the scripts are
full of repo-relative paths (`Path("tests")`, `glob("scripts/seed_*.py")`, bare
`git diff`), and pinning the process cwd makes all of them correct at once,
including in any hook added later.

---

## The guardrails

### Architecture / layering — `scripts/enforce_architecture.py` (PreToolUse: Write|Edit)
Enforces the three-layer boundary (Presentation → Service → Repository):

- Presentation (`pages/`, `theme/`, `frontend.py`, `api/`, `discordbot/`) **must not**
  import from `application.repositories`, and **must not reach through** a service to
  its repository — the content regex catches `service.repository.foo(...)` and
  `self.x_repository.bar(...)` (the attribute must *end* in `repository`, so names
  like `repository_url` never match). The reach-through form is exactly the
  stage-dialog `AttributeError` shape from the 2026-07 audit §1.1.
- `application/repositories/` **must not** import from `application.services`, any
  presentation surface (`pages`, `theme`, `api`, `discordbot`, `frontend`), or `nicegui`.
- `application/services/` **must not** import `nicegui` — **except** files in
  `NICEGUI_ALLOWLIST` (currently `auth_service.py`, which legitimately needs
  `app.storage.user`) — and **must not** import any presentation surface.

Known accepted miss: the reach-through regex also matches inside comments/docstrings
(same tradeoff `enforce_async_safety.py` documents).

### Event-loop safety — `scripts/enforce_async_safety.py` (PreToolUse: Write|Edit)
All users share one asyncio loop, so a single blocking call freezes the app.

- **Repo-wide:** `import requests` / `from requests …` (→ `httpx.AsyncClient`), `time.sleep(...)` (→ `await asyncio.sleep(...)`).
- **Presentation only** (`pages/`, `theme/`, `frontend.py`): `asyncio.create_task(...)` / `ensure_future(...)` (→ `background_tasks.create(...)`). The Discord bot uses raw asyncio legitimately, so it's not checked here.

### Timezone safety — `scripts/enforce_datetime_safety.py` (PreToolUse: Write|Edit)
All datetimes are stored in UTC and shown in US/Eastern, so a tz-naive value
breaks the invariant. Content regex (like `enforce_async_safety.py`):

- Blocked: `datetime.utcnow(...)` (always tz-naive) and **naive** `datetime.now()` /
  `datetime.today()` — an empty arg list, optionally chained (`datetime.now().date()`).
- Allowed: `datetime.now(timezone.utc)`, `datetime.now(eastern)` — a tz argument is present.
- **Skips** `tests/` and `application/utils/timezone.py` (the sanctioned home of raw
  datetime construction). Steers to `application/utils/timezone.py` helpers.

### Aerich migration protection — `scripts/enforce_migration_safety.py` (PreToolUse: Write|Edit)
Files under `migrations/models/` are generated by `aerich migrate`; a hand-edit
desyncs them from the `models/` package and the aerich version table. Blocks any
Write/Edit whose path is under `migrations/models/` → change the model in `models/`
and run `poetry run aerich migrate && poetry run aerich upgrade` instead. (The
PostToolUse reminder to migrate + update `data-model.md` after a model change
already lives in `hooks/doc-reminder.sh`.)

### Audit actor not guarded — `scripts/check_audit_actor.py` (PostToolUse: Write|Edit)
CLAUDE.md: pass `actor: User` explicitly — never guard an audit call with
`if actor:` (a swallowed actor silently drops the audit entry). AST-based: flags an
`if` whose test is an `actor` truthiness/`is None` check **when its body contains a
`write_log(...)` call** (narrow, to avoid flagging unrelated `if actor:`). Skips
`tests/`, `/.claude/`, `audit_service.py`.

### No ORM writes in the UI — `scripts/enforce_no_orm_writes.py` (PostToolUse: Write|Edit)
Presentation may **read** for display but must not **write** to the DB.
AST-based, scoped to presentation files. Flags a write-method call whose
receiver chain is rooted at a **known Tortoise model** (names loaded from the
`models/` package — or a legacy `models.py` — at runtime):

- Blocked: `Match.create(...)`, `User.bulk_create(...)`, `Tournament.filter(id=x).update(...)`, `Tournament.filter(id=x).delete()`.
- Allowed: reads like `Tournament.filter(...).order_by(...)`, `.all()`, `.get(...)` (they don't end in a write method).
- **Deliberately misses** (precision over recall): bare-instance `obj.save()` (receiver type isn't visible) and module-qualified `models.Match.create()`.

### Safe shell commands — `scripts/enforce_safe_commands.py` (PreToolUse: Bash)
Inspects `tool_input.command` and blocks:

- `pip install …` → use `poetry add` (the project is Poetry-managed).
- `git push --force` / `-f` / `--force-with-lease` → no force-pushing shared history.
- `git commit --no-verify` / `-n` → don't skip git's verification.
- `git reset --hard`, `git clean -f`, `git checkout -- .` → irreversible working-tree loss.
- `aerich downgrade` → reverts DB migrations (data loss).
- `rm -rf` → irreversible recursive delete.
- `dropdb`, `DROP TABLE|DATABASE` → data destruction. **Local sessions only** — see below.
- `git add`/`git commit` of `.env`, and `cat`/`head`/`tail`/`xxd`/… of `.env` → never
  commit or dump real secrets (`.env.example` is exempt via a negative lookahead).

Every row is unconditional except the database-drop one, which carries
`local_only=True` and is skipped when `CLAUDE_CODE_REMOTE=true`. The rule exists to
protect a developer's real, long-lived dev database; a web session gets a throwaway
container whose scratch Postgres `/ui-validation` and `/api-validation` are meant to
tear down and rebuild, so enforcing it there blocks legitimate work and protects
nothing. An **unset** marker counts as local — the exemption has to be opted into,
never inferred. `tests/test_hook_safe_commands.py` pins both halves, and asserts the
other destructive rules stay unconditional.

### Audit-action constants — `scripts/check_audit_actions.py` (PostToolUse: Write|Edit)
AST-based. Flags `…write_log(actor, "match.created")` — an audit action passed
as a string literal — and requires an `AuditActions.*` constant instead. Skips
`tests/` and `audit_service.py` itself.

### Slot-context in background tasks — `scripts/check_slot_context.py` (PostToolUse: Write|Edit)
CLAUDE.md > NiceGUI patterns: a coroutine run via `background_tasks.create(...)`
has an empty slot stack, so a `ui.*` call inside it raises *"The current slot
cannot be determined…"*. AST-based, scoped to presentation files. Resolves each
`background_tasks.create(fn(...))` to its locally-defined async `fn`, then flags
any `ui.*(...)` call in `fn` that is **not** wrapped in a **sync** `with <name>:`
block (the fix pattern — capture `context.client` at the call site, pass it into
the coroutine, and restore it with `with client:`). `Client` is sync-only —
`async with client:` raises `TypeError`, and `Client.current` does not exist in
NiceGUI 3.x (see the `enforce_nicegui_client_api.py` hook below). An httpx-style
`async with httpx.AsyncClient() as c:` is a `Call`, not a bare `Name`, so it does
not mask a missing slot guard.

The same hook carries a **second check** over the same coroutines: a read of
`context.client` from *inside* one. The empty slot stack makes that expression
**raise** rather than return `None`, so a handler opening with
`client = context.client` dies on its first statement — silently, with nothing on
screen. There is no guarded position for it (the value is not in the task at all),
so the fix is always to capture it at the call site and pass it in. A UX audit
found the shape live in My Crew, where it had left the volunteer's *Confirm I can
cover this* and *Withdraw* buttons dead; check 1 could not see it, because the
line looks like an ordinary capture and is usually followed by a correct
`with client:`. Tests: `tests/test_hook_background_client.py`.

**Deliberately misses** (precision over recall): coroutines imported from another
module (body not visible) and UI calls reached indirectly through a helper.

### First-party import resolution — `scripts/enforce_import_resolution.py` (Stop + PostToolUse: Write|Edit)
Catches an `ImportError`-at-startup left by a rename/refactor: a `from PKG import old_name`
whose target module no longer defines `old_name` (e.g. the `current_user_from_storage` →
`get_user_from_discord_id` rename that left **four** stale call sites and broke boot). Resolves
**first-party** modules only — those whose top segment maps to a repo file/dir (flat layout,
`package-mode = false`, so first-party detection is by *path existence*, not `__init__.py`). For
each `from MODULE import name` / `import MODULE.SUB`, it resolves `MODULE` to its file and checks
the name against what that module actually provides (top-level `def`/`class`, assignment targets,
its own imports, `__all__`, and submodule files for packages).

- **`Stop` (load-bearing):** whole-repo sweep — the **only** mode that catches a stale import in a
  file the session never touched (which is exactly how this bug class manifests). Derives the repo
  root via `git rev-parse`, drains stdin, walks every `.py` (skips `.git`/`__pycache__`/`.claude`).
- **`PostToolUse: Write|Edit`:** re-checks just the edited file for fast feedback.
- **Fails open** (never flags) on: a third-party/stdlib module, an unresolved module, a
  `from x import *` or module-level `__getattr__` in the target, a parse/read error, a
  namespace-package name, a relative import escaping the repo, or a path under `/.claude/`.
  Measured **0 false positives** across the tree (~1368 import lines).

### Stored-XSS via markdown/html sinks — `scripts/check_markdown_xss.py` (PostToolUse: Write|Edit)
NiceGUI's `ui.markdown()` / `ui.html()` pass raw HTML through unsanitized, so rendering a stored,
user-writable value through them is a stored-XSS sink — the original finding was the stored
tournament `triforce_access_message` being rendered through `ui.markdown()`, letting any staff
member inject script into every viewer's page. AST-based, scoped to presentation files. Flags a
`ui.markdown(arg)` / `ui.html(arg)` whose first positional arg is **not** a pure literal — a
`Constant`, or an f-string / `+`-concat composed only of literals, is allowed; a `Name`/
`Attribute`/`Call` (a variable or model field) is flagged. Reserve the sinks for static literals;
render dynamic text with `ui.label(...).style('white-space: pre-wrap')` or sanitize first.
**Deliberately misses** (precision over recall): module-qualified `nicegui.ui.markdown(x)` (the
receiver root isn't a bare `ui`), same tradeoff the ORM-write hook documents.

### NiceGUI `Client.current` — `scripts/enforce_nicegui_client_api.py` (PreToolUse: Write|Edit)
NiceGUI 3.x exposes the per-request client as `context.client` (`from nicegui import
context`); there is **no** `current` attribute on the `Client` *class*, so `Client.current`
raises `AttributeError: type object 'Client' has no attribute 'current'` the moment the
handler fires. This bites the slot-context fix pattern specifically: capturing the client
for a `background_tasks.create(...)` coroutine with `Client.current` looks right but crashes
at runtime — commit `bca4d7a` introduced exactly this while *fixing* a slot-context error,
and it sat live on `main`. Content regex (like `enforce_async_safety.py`): matches
`\bClient\.current\b` in the incoming fragment and steers to `context.client`. `\bClient`
won't match a longer name (`MyClient.current`), and the class genuinely has no such
attribute, so false positives are **0** (measured: 1 hit across 264 `.py` files — the live
bug itself; `check_slot_context.py`'s doc literal is skipped by the `/.claude/` guard).

### DRY regressions — `scripts/check_dry_regressions.py` (PreToolUse: Write|Edit)
Blocks re-introduction of the copy-paste shapes the 2026-07 code-quality audit
removed, each message naming the shared primitive that replaced the shape:

| Shape | Use instead | Audit |
|---|---|---|
| setattr update loop in a repository | `TenantScopedRepository.update` (`_base.py`) | §2A.2 |
| `def _load_*_or_404` in `api/routers/` | service raises `NotFoundError` → 404 | §2B.1/2B.2 |
| `raise ValueError('… not found')` in a service | `require_found(obj, label)` | §2A.6 |
| literal truthy-env comparison | `env_flag(name)` (`environment.py`) | §3.2 |
| `while True:` + `asyncio.sleep` in a service | `run_worker_loop` / `BackgroundLoop` | §2A.3 |
| `raise NotImplementedError` in services/repos | `ValueError('… not yet implemented')` | §1.3 |
| local `utc`/`make_user`/`app`/`two_tenants`/`stub_discord_queue`/`bypass_auth` in a test module | `tests/factories.py` / conftest | §2D.2–2D.6 |

**Net-new counting** (the reusable idiom for guarding a pattern that still has
legacy occurrences): the hook computes the *proposed* file content (Write's
`content`, or the Edit's replacement applied to the on-disk file), counts regex
matches in old vs new, and blocks only when the count **increases**. Replaying or
editing a legacy file never blocks; adding one more occurrence anywhere always
does — so a rule can ship the day the extraction lands instead of waiting for a
zero baseline. Fails open on malformed payloads, unreadable files, or an Edit
whose `old_string` doesn't match (that Edit fails anyway).

### Slow test fixtures — `scripts/check_fixture_cost.py` (PreToolUse: Write|Edit)
The test suite's wall time is dominated by per-test **fixture setup**, not by
assertions: before commit `f0ceb4b` it was 84% of the run (166s of 197s). Five
shapes have caused it in turn, and all are now built once per worker process and
shared. This hook blocks re-introducing any of them in `tests/`:

| Shape | Use instead |
|---|---|
| mounting `api.router` on a test's own `FastAPI()` app | the `app` fixture in `tests/conftest.py` (returns the `@functools.cache`d `build_api_app()` from `tests/api_helpers.py`) |
| `Tortoise.generate_schemas()` in a test | the `db` fixture, which replays the script rendered once by `_schema_sql()` in `tests/conftest.py` |
| `Tortoise.init()` in a test | the `db` fixture, which inits once per worker and restores a template database per test |
| `build_server()` in a test | `mcp_session()` from `tests/mcp/conftest.py`, which mounts the cached catalogue with a fresh transport |
| `seed_all()` in a test | the `seeded_db` fixture, which snapshots the seeded database once per worker |

The first rule cost ~200ms per test (`include_router` resolves every route's
dependency graph and builds a Pydantic response model per endpoint) across ~400
API tests — 135s of the old 207s suite, more than every DB query in it combined.
Two modules had also re-pasted their own local copy of the `app` fixture,
bypassing the cache.

**The discriminator is mounting the router, not constructing an app.**
`tests/test_public_bracket_access.py`, `tests/test_infra_coverage.py` and
`tests/test_security_hardening.py` all legitimately build throwaway bare
`FastAPI()` apps to exercise middleware and error handlers, so the rule requires
*both* a `FastAPI(` and an `include_router(api.router` and exempts the one
sanctioned builder (`api_helpers.py`) plus `conftest.py`. Verified: 0 violations
across all 163 files in `tests/`, including replaying each of the three
bare-app files (and each with an extra bare app appended) as a from-scratch write.

The last three rules exempt by **path tail** rather than basename, because the
sanctioned builder is a specific conftest: `mcp/conftest.py` owns the cached MCP
catalogue, and `test_seed_coverage.py` keeps its direct `seed_all()` calls
because there the seed *running* is what is under test.

Uses the **net-new counting** idiom from `check_dry_regressions.py` (same `Rule`
dataclass, `_norm`/`in_tests` helpers, and Write/Edit content synthesis) even
though every rule has a zero baseline today — so the rules keep working if a
justified exception is ever added. It is a **separate script** rather than two
more rows in `check_dry_regressions.py` because that file is scoped to the
2026-07 code-quality audit's copy-paste findings; this is a performance
invariant with its own vocabulary, and Design principle 2 (self-contained
scripts) makes the split free. `tests/test_fixture_performance.py` is exempt —
it names the banned shapes in its own prose (the same self-reference gotcha the
`/.claude/` skip exists for), and its AST scan polices it instead.

**This hook is the fast-feedback layer only.** `PreToolUse` never sees a human's
IDE edit or an externally-authored PR, which is most of the risk surface; the
load-bearing layer is `tests/test_fixture_performance.py` below.

### Syntax validity — `scripts/check_syntax.py` (PostToolUse: Write|Edit)
`ast.parse` on the resulting `.py` file; rejects an edit that leaves it
unparseable. This runs first among the AST hooks conceptually — the other AST
hooks exit 0 on a `SyntaxError` so only this one reports it (no double-noise).

### File length — `scripts/check_file_length.py` (PostToolUse: Write|Edit)
Counts lines in the resulting `.py` file. Two tiers: an advisory past 800 lines
and a stronger "must split" message past 1500, both exit 2 to nudge toward
splitting modules along the three-layer pattern. Skips `migrations/`
(aerich-generated).

### Layer exports — `scripts/check_layer_exports.py` (PostToolUse: Write|Edit)
CLAUDE.md "Adding a new feature" step 4 requires exporting new services/repos from
each package's `__init__.py`; forgetting it means `from application.services import
FooService` fails at import. AST-based, scoped to `application/services/*_service.py`
and `application/repositories/*_repository.py`. Two branches:

- **Class module**: the filename-derived PascalCase class (`discord_service` →
  `DiscordService`) must be imported **and** in `__all__` of the sibling `__init__.py`.
- **Functional module** (no `*Service`/`*Repository` class, ≥1 public top-level
  function — the `discord_queue` shape): the module **stem** must be imported
  (`from . import stem`) and listed in `__all__`. This closes the gap that let
  `oauth_handoff_service.py` go unexported for weeks of session-start DOC/EXPORT
  GAP noise.

Skips the `__init__.py` files themselves; fails open on read/parse errors. Known
deliberate miss: acronym-cased primaries (`SpeedGamingETLService` vs the derived
`SpeedgamingEtlService`) are invisible to both branches.

### Hardcoded secrets — `scripts/check_secret_leak.py` (PostToolUse: Write|Edit)
Secrets must come from `os.environ` / `os.getenv`, never be committed as literals.
Flags (1) any string matching the Discord bot-token shape, and (2) AST assignments
to a secret-named variable (`*_SECRET`/`*_TOKEN`/`*_PASSWORD`/`*_API_KEY`, etc.)
whose value is a hardcoded string literal. Low false-positive bias: requires the
literal to be ≥12 chars and not a placeholder (`your…`, `changeme`, `example`,
`<…>`, …). Skips `tests/`, `/.claude/`, and `.env.example`.

### Tenant scoping in repositories and services — `scripts/check_tenant_scoping.py` (PostToolUse: Write|Edit)
CLAUDE.md > Multitenancy: there is no auto-scoping manager, so a forgotten
`scoped(...)` is a **silent cross-tenant leak**. AST-based, covering
`application/repositories/*.py` and `application/services/**.py` (skips
`_tenant.py`, `__init__.py`). Discovers
tenant-scoped models at runtime (any `Model` subclass in `models/` with a
`tenant` field), then flags a read root (`Model.filter/get/get_or_none/all/
first/exists`) that is neither inside a `scoped(...)` call nor passing a
`tenant*` kwarg, and a write root (`create`/`get_or_create`/`update_or_create`)
with no `tenant*` kwarg (checks `defaults={...}` keys too). Escape hatches match
the convention `_tenant.py` documents: a function whose source says
**"cross-tenant"**, **"unscoped"**, or **"global"** is exempt, and
`EXEMPT_MODELS` (`TenantMembership`, `TenantJoinRequest`, `RacetimeBotTenant`)
covers junction tables where the tenant FK is the row's *subject*, not a scoping
stamp.
In a **service** module only *writes* are flagged: services legitimately read a
scoped model directly (the sanctioned load-or-404 shape passes `tenant_id=` and
is checked like any other read), but an unstamped service write is never right —
the tenant FK is non-null, so the insert simply fails, and the `db` fixture's
auto-stamp means no test can see it. That is how the enrolment write in
`UserService` shipped broken.
**Deliberately misses** (precision over recall): `bulk_create` (rows built
elsewhere), instance `obj.save()`, queries built outside these two layers.
Measured **0 false positives** across all 40 repository files and all 108
service files.

### EventType registry & literals — `scripts/check_event_types.py` (PostToolUse: Write|Edit)
CLAUDE.md > Event publishing: `EventType` names are an **external webhook
contract** and `EventType.ALL` drives the webhook UI multiselect + validation.
Two modes: (1) editing `application/events/event_types.py` → checks every
string constant is in `ALL`, every `ALL` entry is a defined constant, and no
two constants share a wire value; (2) any other non-test file → flags
`Event.create('literal', ...)` (mirror of `check_audit_actions.py` — the event
would publish but be invisible to the UI/validation). Fails open if the class
shape changes beyond what it parses. Skips `tests/`, `/.claude/`.

### Migration drift — `scripts/check_migration_drift.py` (Stop)
The mirror of `enforce_migration_safety.py`: that blocks hand-editing generated
migrations; this catches editing the `models/` package and forgetting to generate
one. **Schema-token matching**, not file-touch heuristics: tokens are the names of
newly added `class Foo(Model)` definitions plus any field on an added/removed
`name = fields.…` line in the models diff; evidence is the added diff lines under
`migrations/models/` plus untracked files there. Every token must appear
(case-insensitive substring — aerich migrations name the tables/columns they touch)
or the turn blocks with the missing names and
`poetry run aerich migrate && poetry run aerich upgrade`.

Consequences of token matching: an enum-member/docstring-only model edit produces
zero tokens and passes (the old version demanded a migration aerich would never
generate), and an *unrelated* migration file no longer satisfies the check (the old
version accepted any touched migration). The one residual false positive — moving a
field between model files with no schema change — is exempted with a
`# schema-unchanged` comment on an added line in that model file. Drains stdin
(Stop hooks hang otherwise); fails open if git is unavailable.

### Seed coverage — `scripts/check_seed_coverage.py` (Stop)
The seed-side mirror of `check_migration_drift.py`, enforcing CLAUDE.md
"Adding a new feature" step 6: at Stop, if the working tree adds a **new
Tortoise `Model` class** under `models/` (added `+class Foo(Model)` diff lines
or untracked model files; requires the bare word `Model` in the base list so
enums/dataclasses/pydantic `BaseModel` never match) whose name is not found
(word-bounded) in the concatenated content of the `scripts/seed_*.py` files,
it blocks the turn — a model the seed never creates is invisible to
`/ui-validation` and every dev environment. Merely *touching* the seed file no
longer satisfies it; the model must be named. A genuinely unseedable model is
exempted with a `# seed-exempt: Foo — reason` comment in a seed script (the
name search hits it). The runtime backstop is `tests/test_seed_coverage.py`,
which runs the real seed and asserts the row actually lands. Field edits to an
existing model deliberately do **not** trigger it (noise). Drains stdin; fails
open if git or the seed scripts are unavailable.

### Related tests on edit — `scripts/run_related_tests.py` (PostToolUse: Write|Edit)
Runs just the pytest file matching an edited module so regressions surface in-loop
(CI runs the whole suite separately). Maps `application/services/foo_service.py` →
`tests/services/test_foo_service.py` (and analogous repo/api/test mappings), plus
`scripts/seed_*.py` → `tests/test_seed_coverage.py` and `models/*.py` → the
leak-test ratchet (`tests/tenancy/test_leak_test_coverage.py` — the fast static check;
the full-seed runtime check stays Stop/CI-gated). Runs only test files that exist
with `MOCK_DISCORD=true poetry run pytest -q <file>`, and exits 2 with the captured
output on failure. A **timeout is exit 2**, not a pass — the message says the
result is UNKNOWN and gives the command to run by hand (110s margin under the 120s
hook timeout). Fails open only when no matching test exists or poetry is missing
(environment conditions, not test results).

### Full suite at turn end — `scripts/run_full_tests.py` (Stop)
Runs `poetry run pytest -q` at Stop, but **gated** like `doc-check.sh`: only when
`git diff`/untracked shows a changed non-test `.py` under `application/`, `api/`,
`pages/`, `theme/`, `discordbot/`, `models/`, or `frontend.py`. Blocks the turn
with the captured output on failure. A **timeout is exit 2**, not a pass: the
suite runs ~140s against a 270s budget (300s hook timeout), so expiry genuinely
signals a hang and the message says the Stop gate did NOT verify the changes —
the old version silently exited 0 on timeout, which by mid-2026 meant it was
silently verifying nothing (the suite had outgrown its 110s budget). Fails open
only on missing poetry. Drains stdin.

### Tests as guardrails (pytest, ride the Stop gate AND CI)
Some invariants are enforced as ordinary tests rather than hook scripts — they run
in `run_full_tests.py` at Stop *and* in CI, so they also bind human contributors:

- **`tests/test_seed_coverage.py`** — runs the real `scripts/seed_dev.py`
  `seed_all()` against the in-memory harness and asserts every tenant-FK model has
  a row for the default tenant (plus an idempotency re-run). The claim "the seed
  covers every model" is an invariant, not prose.
- **`tests/tenancy/test_leak_test_coverage.py`** — ratchet: every tenant-FK model must
  appear in a `tests/*isolation*` file or carry a justified `BACKLOG` entry; a
  companion test forces stale entries out, so the backlog only shrinks.
- **`tests/test_feature_flags.py`** — registry parity: every `FeatureFlag` member
  has a `FeatureFlagSpec` (why there is no separate hook for it).
- **`tests/test_hook_cwd_independence.py`** — the guardrails' own guardrail, and
  necessarily a test rather than a hook: a hook cannot check whether hooks still
  run, since the failure mode *is* the hook not running. It asserts every
  `settings.json` command routes through `$CLAUDE_PROJECT_DIR` and names a file
  that exists, every `scripts/*.py` calls `anchor()`, no `hooks/*.sh` resolves
  the root with `git rev-parse --show-toplevel`, and — end to end — that
  `enforce_architecture.py` still returns 2 for a violation and 0 for clean code
  when run from an unrelated cwd, with and without `$CLAUDE_PROJECT_DIR` set.
- **`tests/test_fixture_performance.py`** — the load-bearing half of
  `check_fixture_cost.py` above. The hook only fires when Claude Code writes a
  file, so this module re-asserts the same invariants for every contributor:
  (1) **cache identity** — `build_api_app() is build_api_app()` and
  `_schema_sql() is _schema_sql()`, plus a `cache_info` check, so removing a
  `@functools.cache` fails by name even when no new fixture is added; that the
  engine is already built and the running test is on the shared connection with
  its template intact; and that `mcpserver.mount()` still resolves to the cached
  MCP catalogue and gets a fresh session manager with it;
  (2) a **single AST pass** over `tests/` asserting no module but `conftest.py`
  defines a fixture named `app` (the direct guard against the re-pasted
  fixture), that nothing but `api_helpers.py` mounts the API router, that no
  test calls `generate_schemas`, `Tortoise.init`, `build_server` or `seed_all`
  outside the one file that owns each, and that no fixture is a bare
  `return build_api_app()` alias — the shape a local `app` fixture takes once
  renamed. Fixtures that *assemble* a context and merely include the cached app
  in a returned dict (`tests/api/test_speedgaming.py`) are deliberately not
  flagged: the app is cached, so that costs nothing. Deliberately **not**
  timing-based — a wall-clock budget is flaky on shared runners, and a flaky
  guard gets deleted. Costs ~0.3s of a ~20s suite (AST-only, one pass, cached).
- **conftest `_no_external_network`** — autouse socket guard: any non-loopback
  `connect` raises, so a test reaching a real host fails by name instead of
  passing online and flaking offline.

### Re-running the bug-history audit — `commands/guardrail-audit.md`
The guardrails above were derived by mining the project's bug history for recurring
(often AI-generated) failure modes and adding a mechanical check for each. The
`/guardrail-audit` slash command re-runs that process: it mines both the git history
**and** the local Claude Code session transcripts (`~/.claude/projects/<repo>/*.jsonl`,
which capture in-session fixes that never became a commit — a strictly larger sample
than git), builds a taxonomy, cross-references the existing hooks, and adds guardrails
for any uncovered, mechanically-detectable class. Run it **locally** (the transcripts
don't exist in a fresh CI/web container). Its sibling `/code-quality-audit` (see
Skills & agents below) mines the *codebase* rather than the session history; the two
feed the same hook pipeline.

### Pre-existing doc automation — `hooks/*.sh`
Not guardrails (advisory, never block): `session-start.sh` audits source-vs-doc
coverage at session start; `doc-reminder.sh` nudges to update docs after edits;
`doc-check.sh` runs at Stop. All three take `$REPO` from `hooks/_repo.sh`; being
advisory, a bad root would have degraded them to silence rather than an error.

---

## Skills & agents

Beyond the hooks (which *block* mistakes), `skills/` and `agents/` give Claude
procedural knowledge (how to do a thing right the first time). Together they
cover the feature lifecycle end to end — plan → implement → test → review:

- **`skills/plan-feature/`** — step **-1**: turn a feature request into a
  reviewed design brief (flag decision, model + tenant impact, layer
  touchpoints naming the shared primitives, test plan incl. leak tests, seed
  and docs touchpoints, open questions) and stop for user sign-off before any
  code.
- **`skills/add-feature/`** — the end-to-end implementation checklist:
  model → migration → repository (tenant scoping, `TenantScopedRepository`) →
  service (audit + events, `require_found`) → exports → UI/API (shared
  admin-CRUD/dialog helpers, no router preloads) → dev seed → tests (incl.
  leak-test ratchet) → `/ui-validation` + `/api-validation` → docs. Sequenced
  to match the hooks, so following it never trips one.
- **`skills/ui-validation/`** — headless-browser validation loop for
  presentation changes (Postgres + seed + MOCK_DISCORD login + Playwright);
  the only way to exercise client-side Vue/Quasar slot templates.
- **`skills/api-validation/`** — the API counterpart: boots the real server,
  seeds, and drives endpoints with the deterministic seeded bearer tokens —
  401/403/404 matrix, response shape, and the cross-tenant-404 live leak
  probe that in-process ASGITransport tests can't exercise end to end.
- **`skills/discord-ux/`** — the Discord counterpart: the bot's DM/button
  surface can't be driven headlessly (and `MOCK_DISCORD` never connects), so
  this reconstructs it by rendering the real message builders
  (`render_surface.py`) and reproducing Discord's DM chrome, with a tenant-safety
  / duplicate-field / spacing / embeds UX checklist. Use to review what the bot
  sends.
- **`agents/architecture-reviewer.md`** — a read-only review subagent for the
  **judgment** calls the mechanical hooks can't make: business logic at the
  wrong layer altitude, tenant-scoping *semantics* (missing `tenant_scope` in
  workers, unjustified cross-tenant reads), audit/event coverage gaps,
  shared-primitive drift (admin tabs off `admin_crud.py`, workers off
  `run_worker_loop` or missing their feature-flag skip, cloned OAuth
  providers), error contract incl. the toast convention, NiceGUI shared-state
  pitfalls, missing leak tests/seed rows. Use after a cross-layer feature or
  before committing; it reports, never edits.
- **`commands/code-quality-audit.md`** — `/code-quality-audit` runs a
  whole-codebase DRY & engineering-practices audit: fan-out per-section
  reviewers, adversarial reconciliation, a report in `docs/reviews/`,
  leverage-ordered remediation waves, and recurring mechanical classes fed back
  into hooks (`check_dry_regressions.py` is that loop's output). Past reports
  are not retained once remediated — they go stale by design and git history
  keeps them.

---

## Design principles (apply to any new guardrail)

1. **Fail open.** On malformed stdin, a missing `file_path`, a non-`.py` file,
   an unreadable file, or a `SyntaxError`, **exit 0**. Only a *real* violation
   exits 2. A buggy hook must never wedge all edits.
2. **Self-contained scripts.** Each script re-implements the ~10-line
   stdin/extract idiom rather than sharing a module, so any hook can be added or
   removed independently. The small duplication is intentional.
3. **Low false-positive bias.** Prefer precision (e.g. anchoring ORM writes to
   known model names) over catching everything. A noisy guardrail gets disabled.
4. **Skip `.claude/`.** Content checks must ignore files under `/.claude/` —
   otherwise a hook flags its own pattern literals (see Gotchas).

---

## Adding or adjusting rules

- **New layer/import rule:** extend `classify()` / `check()` in
  `enforce_architecture.py`.
- **Allow a specific file to break a rule:** the clean pattern is an allowlist
  set keyed by basename, like `NICEGUI_ALLOWLIST = {"auth_service.py"}` in
  `enforce_architecture.py`. For the other scripts, add an early skip near the
  top of `main()`, e.g.:
  ```python
  if file_path.replace("\\", "/").endswith("/some_special_file.py"):
      sys.exit(0)
  ```
- **New blocked command:** add a `Rule(compiled_regex, name, fix)` row to `RULES` in
  `enforce_safe_commands.py`. Pass `local_only=True` only when the danger is a
  developer's own machine and the rule would be pure friction in a throwaway web
  container — the default (enforce everywhere) is the right one for almost everything.
- **Register a new hook:** add a `{ "type": "command", "command": "python3
  \"${CLAUDE_PROJECT_DIR:-.}/.claude/scripts/check_foo.py\"", "timeout": 10 }`
  entry under the right matcher in `settings.json`, and start the script with
  `from _hook_paths import anchor` / `anchor()` (see [Hooks must never depend on
  the working directory](#hooks-must-never-depend-on-the-working-directory) —
  both halves are enforced by a test). Multiple hooks per matcher all run; any
  exit 2 wins.

---

## Testing the hooks

Each script reads stdin and exits 0/2, so you can test it directly:

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"pages/x.py","content":"from application.repositories.user_repository import UserRepository\n"}}' \
  | python3 .claude/scripts/enforce_architecture.py ; echo "exit: $?"   # -> 2
```

The PostToolUse AST scripts read the file from disk, so stage a real file first
(`printf '…' > pages/_probe.py`) and point `file_path` at it.

The scripts anchor their own cwd, so the invocation above works from any
directory — but the `.claude/scripts/…` path in the example is itself relative,
so either run it from the repo root or spell the script path out in full.

### Gotchas we hit (self-reference)

- **A content hook will flag its own example literals.** `enforce_async_safety.py`
  contains the string `time.sleep` etc.; it skips `/.claude/` so editing the
  hook scripts doesn't trip them.
- **The Bash guard scans the command *text*,** so a command that merely
  *mentions* `pip install` (a test script, a here-doc) is blocked. To run the
  test suite, put it in a **script file** and run `bash test.sh` — inner
  subprocesses aren't intercepted, only the top-level Bash tool call is.
- **Committing is a Bash command too.** A commit message describing the blocked
  patterns trips the guard. Use `git commit -F <file>` (write the message with
  the Write tool) so the literals live in a file, not on the command line.
- **A `cd` in a Bash call used to brick the session.** The hook commands were
  relative (`python3 .claude/scripts/…`), and the Bash tool's cwd persists
  between calls — so one `cd pages/` made every subsequent `Write`, `Edit`, and
  `Bash` call fail its own PreToolUse guard with `can't open file`, exit 2,
  *blocked*. There is no way to `cd` back out, because that too is a Bash call.
  Fixed by the two anchoring rules above; recovering a session stuck this way
  needs a tool that isn't behind the broken matcher.

---

## Why we did **not** add ruff

We considered a `ruff check --select ASYNC` hook (ruff 0.15.8 is already
installed at `/root/.local/bin/ruff`) and **decided against it**:

- **Overlap.** Ruff's `ASYNC` ruleset overlaps `enforce_async_safety.py`, which
  already blocks the common event-loop blockers. The marginal gain (catching
  blocking calls beyond the three hardcoded patterns) didn't justify a new
  dependency in the hook chain.
- **Fragility as a self-contained hook.** A hook calling a globally-installed
  `ruff` works in this environment but silently does nothing where ruff isn't on
  PATH — an inconsistent guardrail.
- **Cost of doing it "properly."** Full integration means adding `ruff` to
  `pyproject.toml` dev deps + a `ruff.toml` + a CI step. That's a broader
  project/tooling change (affects all contributors and CI), and `poetry run
  ruff` here hits the project's `^3.12` vs the env's 3.11 mismatch, making it
  finicky to land.

**If revisited:** the right move is full integration (pyproject dep + config +
CI lint step) so linting is consistent for everyone — not a hook leaning on an
ad-hoc local binary. Until then, the regex `enforce_async_safety.py` covers the
high-value cases.
