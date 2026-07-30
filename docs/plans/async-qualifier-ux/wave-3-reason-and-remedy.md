# Wave 3 — a decision with a reason, and a remedy someone can spend

**Read [README.md](README.md) first. Waves 1–2 must be merged.**

Everything this wave needs already exists in the service and is already exposed
over REST. `review_run` takes a `note` no page passes; `reattempt_run` has no
caller in `pages/` at all. This wave wires both, and adds the one thing genuinely
missing: a way for a reviewer to spend a reattempt on a runner's behalf.

| Task | Touches | Size |
|---|---|---|
| T3.0 | *(conditional)* split `admin_qualifiers.py` into a package | small |
| T3.1 | rejecting requires a reason (service + REST) | small |
| T3.2 | the review dialog that collects it | medium |
| T3.3 | the runner sees the reason — page and DM | medium |
| T3.4 | the runner spends their own reattempt | medium |
| T3.5 | a reviewer grants one, from a Runs tab | large |
| T3.6 | seed + docs | small |

Closes **F4**, the reattempt half of **F1**, and the remaining context part of
**F5**.

---

## T3.0 — Split the admin page first, if it is going to get long

`pages/admin_tabs/admin_qualifiers.py` is 496 lines and this wave adds a tab and
two dialogs. `check_file_length.py` advises over 800. If your additions push it
past ~700, split it **before** adding, mirroring
[`pages/admin_tabs/admin_brackets/`](../../../pages/admin_tabs/admin_brackets/):

```
pages/admin_tabs/admin_qualifiers/
    __init__.py      # re-export admin_qualifiers_page
    page.py          # shell, list view, qualifier dialog, loaders
    manage.py        # the detail drill-down: tabs, pools, live races
    review.py        # the review queue + its dialog          (T3.2)
    runs.py          # the all-runs tab + grant reattempt     (T3.5)
    shared.py        # _fmt, badge colours
```

`pages/admin.py` imports `admin_qualifiers_page`; keep that import path working
through `__init__.py` so the tab registration
([`admin.py:138`](../../../pages/admin.py#L138)) does not change.

Do this as its own commit with no behaviour change, or skip it and say why.

---

## T3.1 — A rejection requires a reason

**File:** `application/services/async_qualifier/async_qualifier_service.py`,
`review_run` ([`:615-650`](../../../application/services/async_qualifier/async_qualifier_service.py#L615)).

```python
        note = (note or '').strip()
        if not approved and not note:
            raise ValueError("A rejection needs a reason — the runner is told what you write here.")
        if note:
            await self.note_repository.create(run_id=run.id, author_id=actor.id, note=note)
```

Approve keeps its optional note. Put the validation **above** the note write and
above the status update, so a rejection with no reason changes nothing at all.

The error sentence names the consequence rather than the field, because the
consequence is the reason for the rule: what the reviewer types is what the
runner reads.

### REST

`ReviewRequest.note` stays `Optional[str]` in the schema — the requirement is
conditional on `approved`, which is a service rule, not a shape rule, and putting
it in Pydantic would duplicate it. The 400 comes from the service through the
existing error route.

`tests/api/test_async_qualifiers.py` almost certainly has a reject call with no
note; it will now 400. Update it, and add the pair:

```python
async def test_reject_without_a_reason_is_a_400(...)
async def test_reject_with_a_reason_stores_a_note(...)
```

### Tests

`tests/services/test_async_qualifier_service.py`:

```python
async def test_rejection_requires_a_reason(db)                 # ValueError, exact message
async def test_rejection_with_a_reason_stores_a_note(db)
async def test_rejection_without_a_reason_changes_nothing(db)  # review_status still PENDING
async def test_approval_still_works_without_a_note(db)
```

The third is the one worth writing carefully — it is what proves the check sits
before the mutation.

---

## T3.2 — The dialog that collects it

**File:** the review queue (`review.py` after T3.0, else
`admin_qualifiers.py::_render_queue`).

Both buttons now open one dialog rather than firing immediately:

- **Approve** → note field labelled *"Note (optional)"*, confirm **Approve run**,
  `tone='positive'`.
- **Reject** → the same dialog with *"Reason (shown to the runner)"*, confirm
  **Reject run**, `tone='negative'`, and the confirm disabled until the field is
  non-blank. Keep the service check anyway — the page is not the authority.

Build it as one `_open_review_dialog(run, approved: bool)` so the two paths cannot
drift; it calls the existing `_review(run_id, approved, note)` handler, which
gains the `note` argument and passes it through. `notify_error` on failure, the
existing `ui.notify('Run approved'/'Run rejected')` on success, then
`load_detail()`.

Use `ui.textarea` with `rows=3`, not `ui.input`: a reason worth reading is longer
than one line, and this is the text the runner receives.

### While you are in this card — the rest of F5

The reviewer decides from four facts today. Wave 2 added the two durations and
the timestamps. Add the remaining context here:

- **the permalink played** — `run.permalink.url` as a link (the card already
  reaches `run.permalink.pool.name`, so it is prefetched), truncated the way
  `_render_pools` truncates URLs;
- **the runner's other runs in this qualifier** — a caption line
  *"Player Two: 2 other runs in Bonus Pool (1 approved, 1 forfeit)"*. Source it
  from the same `list_for_qualifier` read T3.5 adds; if T3.5 is not done yet,
  do this line in T3.5 instead of adding a second query here;
- **existing notes on the run**, if any — a rejected-then-reattempted run can
  already carry one, and re-reviewing without seeing the earlier note is how a
  reviewer contradicts a colleague.

### Tests

Assert the dialog exists and that reject cannot be submitted blank — if the page
has no unit harness, the service test in T3.1 is the safety net and the browser
check below is the verification. Say which you relied on.

---

## T3.3 — The runner is told why, on the page and in the DM

### The page

**Files:** `application/repositories/async_qualifier_repository.py`
(`list_for_user`, [`:103-106`](../../../application/repositories/async_qualifier_repository.py#L103))
and `pages/qualifiers.py::_render_my_runs`.

```python
        return await scoped(
            AsyncQualifierRun.filter(qualifier_id=qualifier_id, user_id=user_id)
        ).prefetch_related('permalink__pool', 'review_notes__author').order_by('-created_at')
```

Add a **Reviewer note** column to the runs table showing the most recent note's
text (empty when there is none), and its `field_slots` entry if it needs
wrapping. This is not a disclosure change: `get_run_notes`
([`:652-660`](../../../application/services/async_qualifier/async_qualifier_service.py#L652))
already permits a run's own owner to read its notes — the page simply never
asked. Keep `get_run_notes` for the REST client.

At 390px the note is the longest field on the card; check it wraps rather than
stretching the card, and put it **last** in the column order so the mobile card
reads status → time → score → why.

### The DM

**File:** `_notify_run_reviewed`
([`:741-754`](../../../application/services/async_qualifier/async_qualifier_service.py#L741)).

*"Your qualifier run was rejected."* becomes the verb, the reason, and a way
back:

```
Your qualifier run was rejected.

Reason: the VoD cuts off before the final boss, so the finish time can't be verified.

Dev Async Qualifier → https://…/t/default/qualifiers/1
```

Build the link with `tenant_url(run.tenant, f'/qualifiers/{run.qualifier_id}')`
(`from application.utils.tenant_urls import tenant_url`) — see
`application/services/_bracket/notifications.py` for the precedent. Extend the
existing `fetch_related` to cover `tenant` and `qualifier`. An approval keeps a
short DM and includes the note only when one was left.

The whole method stays inside its `try/except Exception` — a DM must never block
a review, which is why it is written that way today.

### Tests

```python
async def test_runner_runs_carry_their_review_notes(db)          # repository prefetch
async def test_rejection_dm_includes_the_reason(db)              # stub the Discord queue
```

`tests/conftest.py` has a `stub_discord_queue` fixture — use it rather than
patching `DiscordService` by hand (`check_dry_regressions.py` blocks re-defining
hoisted fixtures locally).

---

## T3.4 — The runner spends their own reattempt

### The allowance read

`AsyncQualifierService`, beside `_count_reattempts`
([`:732-734`](../../../application/services/async_qualifier/async_qualifier_service.py#L732)):

```python
    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_reattempt_allowance(self, user: User, qualifier_id: int) -> ReattemptAllowance:
        """How many reattempts this player has spent and may still spend."""
```

`ReattemptAllowance` is a frozen dataclass (`spent`, `allowed`, `remaining`) —
put it beside `LeaderboardEntry`'s style, in the service module or in
`async_qualifier_rules.py`; it carries no I/O. **The `@requires_feature`
decorator is not optional**: `check_feature_flag_gating.py` requires it on every
public entry method in this package, and a top-level read without it is how a
flagged subsystem leaks.

### The page

**File:** `pages/qualifiers.py`.

1. **`_render_my_runs`** gains a per-row **Reattempt** action on a run that is
   terminal, not already `reattempted`, and while `remaining > 0`. Pass it to
   `enable_mobile_grid(..., actions=…)` so the button exists on a phone — the
   audit's whole point about row actions off-screen. It opens a dialog with a
   **required** reason field (`ui.textarea`, `rows=2`) and calls
   `service.reattempt_run(user, run.id, reason=…)`, then `render.refresh()`.

2. **Offer it only while the window is open.** `reattempt_run` itself does not
   check the window and should not start to — a reviewer may need to void a run
   after close (T3.5). But a runner who voids a run they can no longer re-run has
   simply deleted their own score, so the *page* hides the action once
   `_window_open(qualifier)` is false. Comment the reason where you hide it.

3. **The forfeit dialog gets its promised sentence** (wave 1 T1.3 deliberately
   left it out): append *"You have 1 reattempt remaining after this."* when
   `remaining > 0`, and nothing when it is zero. Never write "you can undo this"
   — a reattempt is a fresh draw on a new permalink, not an undo.

4. **Say how many are left**, once, near "My runs": *"Reattempts: 1 of 1
   remaining."* A remedy nobody knows about is the finding this closes.

### Tests

```python
async def test_reattempt_allowance_counts_spent_and_remaining(db)
async def test_reattempt_frees_the_pool_slot_for_a_new_draw(db)
```

The second is the behaviour the runner actually cares about and no existing test
asserts it end to end: forfeit → reattempt → `get_player_pools` offers that pool
again → `start_run` succeeds with a *different* permalink.

---

## T3.5 — A reviewer grants one, from a list of runs

### Why a new method

`reattempt_run` requires `run.user_id == user.id`
([`:563`](../../../application/services/async_qualifier/async_qualifier_service.py#L563))
and is capped by `allowed_reattempts`. Neither fits a reviewer fixing a
mis-click: the reviewer is not the runner, and charging the override to the
runner's allowance defeats its purpose. Same effect, different authorization and
different accounting ⇒ a second entry point over one shared internal.

```python
    async def _void_run(self, run: AsyncQualifierRun, *, reason: str) -> AsyncQualifierRun:
        """Mark a terminal run reattempted, freeing its pool slot, and refresh par."""
```

Both public methods do their own checks, then call it. Move the existing
`reattempted=True` update plus the `recompute_par_and_scores` call
([`:576-582`](../../../application/services/async_qualifier/async_qualifier_service.py#L576))
into it — the par refresh is the easiest half to forget in a new path, and
forgetting it leaves a voided run in the scoring inputs.

```python
    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def grant_reattempt(self, actor: Optional[User], run_id: int, *, reason: str) -> AsyncQualifierRun:
        """Void a runner's terminal run on their behalf, ignoring their allowance.

        The reviewer's override for a mis-clicked forfeit or a bad seed. Requires
        qualifier-admin (``_require_reviewable``) and a reason; unlike
        ``reattempt_run`` it does not consume ``allowed_reattempts``, because the
        run being voided is not the runner's mistake.
        """
```

Guard the same run-state rules as `reattempt_run` (already voided → `ValueError`;
not terminal → `ValueError`), and audit under a **new** action:

```python
    ASYNC_QUALIFIER_REATTEMPT_GRANTED = 'async_qualifier.reattempt_granted'
```

on `AuditActions` (a bare string literal trips `check_audit_actions.py`), with
details `{'run_id', 'qualifier_id', 'target_user_id', 'reason'}`. `write_log`
only — `reattempt_run` publishes no event either, and adding one member to
`EventType` for a reviewer override that has no subscriber is contract surface
for nothing. If you decide it does need an event, use
`AuditService.write_and_publish` and add to both `EventType` and `EventType.ALL`.

Also DM the runner: their pool slot just changed under them. Reuse the shape of
`_notify_run_reviewed` (best-effort, swallowed, `tenant_url` link) — *"A reviewer
granted you another attempt at Bonus Pool. Reason: …"*.

### The Runs tab

A reviewer cannot reach a forfeited run today: `list_pending_review` returns only
`FINISHED` + `PENDING` rows, and a forfeit is written straight to
`APPROVED`/score 0. So the grant needs a surface.

Add a **Runs** tab to the Manage drill-down, between *Review Queue* and
*Leaderboard*:

```python
    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def list_runs(self, actor: Optional[User], qualifier_id: int) -> List[AsyncQualifierRun]:
        """Every run in the qualifier, for the reviewer's runs list."""
```

admin-gated via `access.ensure_qualifier_admin`, backed by the existing
`run_repository.list_for_qualifier` ([`:108-111`](../../../application/repositories/async_qualifier_repository.py#L108)) —
which already prefetches `user` and `permalink__pool`. Load it in `load_detail`
alongside `queue`.

A `ui.table` + `enable_mobile_grid`, columns: Player, Pool, Status, Review, Time
(`format_hms`), Timed, Score, and a **Grant reattempt** row action shown for a
terminal, non-voided run. A voided row is marked *(voided)* and offers nothing.
The dialog collects a required reason, exactly like T3.4's.

This table is also the source for T3.2's *"the runner's other runs"* caption —
one read, two consumers.

### REST

```
POST /async-qualifiers/runs/{run_id}/grant-reattempt   body: {reason}
GET  /async-qualifiers/{qualifier_id}/runs
```

beside the existing reattempt route
([`api/routers/async_qualifiers.py:307`](../../../api/routers/async_qualifiers.py#L307)),
`require_write_actor` for the grant and `require_api_actor` for the list, reusing
`ReattemptRequest` for the body and `AsyncQualifierRunResponse` for both. Tests
for the happy path, the non-admin 403, and the not-terminal 400.

### Tests

```python
async def test_grant_reattempt_requires_qualifier_admin(db)
async def test_grant_reattempt_ignores_the_runners_allowance(db)   # allowed_reattempts=0
async def test_grant_reattempt_requires_a_reason(db)
async def test_grant_reattempt_refreshes_par_and_scores(db)        # the shared internal
async def test_grant_reattempt_frees_the_slot_after_a_forfeit(db)  # the F1 scenario, end to end
async def test_list_runs_requires_qualifier_admin(db)
```

The second and last are the wave's real assertions: the override must work
precisely where the runner's own allowance cannot, and the mis-clicked forfeit
must become recoverable.

---

## T3.6 — Seed + docs

**Seed.** `scripts/seed_online.py::_seed_qualifiers` needs the states these
surfaces are about, none of which it creates today:

- a **rejected** run with a reviewer note (so the runs table's note column and
  the DM copy have something to render);
- a **forfeited** run for `player_three` — the F1 scenario, sitting in the Runs
  tab waiting for a granted reattempt;
- a **voided** run (`reattempted=True`, with a reason) so the *(voided)* row and
  the freed-slot path are both visible;
- keep the qualifier's `allowed_reattempts` at 1 so the runner's own path is
  reachable too.

Idempotent (`get_or_create` / filter-then-create, as the file already does) and
tenant-stamped.

**Docs.**

- [`docs/features/online-tournaments.md`](../../features/online-tournaments.md) —
  the review loop end to end: a rejection needs a reason, the runner sees it on
  the page and in a DM, and the two reattempt paths with their different
  accounting.
- [`docs/reference/services.md`](../../reference/services.md) —
  `get_reattempt_allowance`, `grant_reattempt`, `list_runs`.
- [`docs/reference/rest-api.md`](../../reference/rest-api.md) — the two new
  routes and the conditional-note 400.
- [`docs/features/audit-logging.md`](../../features/audit-logging.md) — the new
  `async_qualifier.reattempt_granted` action.
- [`docs/reference/data-model.md`](../../reference/data-model.md) — one line, if
  it describes `reattempted` / `reattempt_reason`: both paths that set them.

---

## Wave 3 wrap-up

```bash
poetry run pytest
scripts/ui_flag_sweep.sh
poetry run python scripts/seed_dev.py
```

Then, in two browser contexts at both widths — this is the wave where one
person's action is another person's screen, so drive it as a single story:

1. As `player_two`, submit a run.
2. As `staff_user`, **Reject** it with the confirm blank → refused. Type a
   reason → rejected.
3. As `player_two`, reload: the runs table shows `rejected` **and** the reason.
   Check the `MOCK_DISCORD` log for the DM with the reason and the link.
4. As `player_two`, **Reattempt** that run with a reason → the pool is offered
   again → start a run → the permalink is a **different** one.
5. Forfeit it (the dialog now names the remaining reattempts, which should read
   `0` — spend was in step 4).
6. As `staff_user`, open **Runs**, find the forfeit, **Grant reattempt** with a
   reason.
7. As `player_two`, the pool is available again despite `allowed_reattempts`
   being spent. That is F1 closed, observed rather than inferred.

Suggested PR split: *"Require a reason to reject a qualifier run, and tell the
runner"* (T3.1–T3.3), *"Let a runner spend a reattempt"* (T3.4), *"Let a reviewer
grant a reattempt"* (T3.5).
