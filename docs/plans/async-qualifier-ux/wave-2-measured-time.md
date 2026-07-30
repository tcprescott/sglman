# Wave 2 — the server's own clock becomes evidence

**Read [README.md](README.md) first. Wave 1 must be merged.**

The server times every run — that is why the elapsed clock survives a reload and
an offline gap — and then discards the measurement at submit. This wave stores
it, uses it to refuse the impossible and question the implausible, and puts it in
front of the reviewer. It does **not** correct anybody's time.

| Task | Touches | Size |
|---|---|---|
| T2.1 | `measured_seconds` column + migration | small |
| T2.2 | the claim classifier (pure rules) | small |
| T2.3 | `submit_run` stores the measurement and refuses the impossible | medium |
| T2.4 | the page asks about the implausible | medium |
| T2.5 | the reviewer card shows claimed, measured and drift | small |
| T2.6 | REST + seed + docs | small |

Closes **F2**, and the measured-duration/timestamps half of **F5**.

---

## T2.1 — Store the measurement

**File:** `models/async_qualifier.py`, `AsyncQualifierRun` beside
`elapsed_seconds` ([`:146-147`](../../../models/async_qualifier.py#L146)).

```python
    # Wall-clock seconds from the server-stamped ``started_at`` to the moment the
    # player submitted. Stored beside the claimed ``elapsed_seconds`` rather than
    # replacing it: the timer starts at the draw and keeps running while the
    # player reads the seed, pauses, and gets around to submitting, so measured
    # is an upper bound on the real run — evidence for the reviewer, not the
    # result. Null for runs captured from a live race and for pre-existing rows.
    measured_seconds = fields.IntField(null=True)
```

```bash
poetry run aerich migrate --name add_run_measured_seconds
poetry run aerich upgrade
```

**Read the generated migration before continuing.** It must add exactly one
nullable column to `asyncqualifierrun`. Anything else means the working tree has
unrelated model drift — stop and investigate.

> **Migration numbering hazard, learned the hard way.** `aerich migrate` unlinks
> any existing version file that shares the numeric prefix it computes, and it
> computes that prefix from the `aerich` table's *insertion order*, not the
> filename. On a branch where migrations were renumbered after a merge, it has
> silently deleted an existing migration file. After generating, run
> `git status migrations/` and confirm the only change is your new file (the
> newest today is `42_20260729165905_add_match_needs_review.py`).

No backfill. An existing run's measurement cannot be reconstructed — it was
never stored — and a guessed value would be indistinguishable from a real one on
the reviewer's card. Null renders as `—`, which is the truth.

---

## T2.2 — Classify a claim (pure, no I/O)

**File:** `application/services/async_qualifier/async_qualifier_rules.py` — the
established home for side-effect-free predicates.

```python
# Clock skew between the browser's submit and the server's ``now``, plus request
# latency. A claim inside this much of the measured duration is not a discrepancy.
CLOCK_GRACE_SECONDS = 120

# How far a claim may fall short of the measurement before the player is asked
# about it. Generous on purpose: finishing and submitting twenty minutes later is
# ordinary, while a dropped H segment is off by an hour or more.
IMPLAUSIBLE_DRIFT_SECONDS = 15 * 60


class ClaimVerdict(str, Enum):
    OK = 'ok'
    IMPLAUSIBLE = 'implausible'   # ask the player; never blocks
    IMPOSSIBLE = 'impossible'     # refuse; the claim exceeds the wall clock


def classify_claim(claimed_seconds: int, measured_seconds: Optional[int]) -> ClaimVerdict:
    """Compare a claimed finish time against the server-measured wall clock."""
```

The rule, in full:

| Condition | Verdict |
|---|---|
| `measured_seconds` is `None` | `OK` — nothing to compare against |
| `claimed > measured + CLOCK_GRACE_SECONDS` | `IMPOSSIBLE` |
| `measured - claimed >= IMPLAUSIBLE_DRIFT_SECONDS` | `IMPLAUSIBLE` |
| otherwise | `OK` |

`IMPOSSIBLE` is safe to refuse because `measured` is an upper bound by
construction: a run cannot have taken longer than the time since it started.
`IMPLAUSIBLE` must **not** refuse — a player who finishes and submits an hour
later is legitimate and would otherwise be locked out of submitting at all.

Add the message builder beside it so both the service and the page say the same
thing:

```python
def describe_claim(claimed_seconds: int, measured_seconds: int) -> str:
    """One sentence naming both numbers, for the refusal and the prompt."""
```

It returns e.g. *"Your run has been going 0:14:22, so a finish time of 1:14:22
is longer than the run itself."* Import `format_hms` from
`application.utils.duration` — a `utils` import from a service helper is the
right direction (the reverse would not be).

### Tests

`tests/services/test_async_qualifier_rules.py` (create if absent) — a
`parametrize` over the four rows above plus the boundaries: exactly
`measured + CLOCK_GRACE_SECONDS` is `OK`, one second more is `IMPOSSIBLE`,
exactly `IMPLAUSIBLE_DRIFT_SECONDS` of drift is `IMPLAUSIBLE`. Pure functions,
no `db` fixture.

---

## T2.3 — `submit_run` measures, stores, and refuses the impossible

**File:** `application/services/async_qualifier/async_qualifier_service.py`,
`submit_run` ([`:511-535`](../../../application/services/async_qualifier/async_qualifier_service.py#L511)).

```python
        run = await self._require_own_active_run(user, run_id)
        if elapsed_seconds is None or elapsed_seconds <= 0:
            raise ValueError("Finish time must be a positive number of seconds")
        if elapsed_seconds > MAX_RUN_SECONDS:
            raise ValueError("Finish time is longer than a week — check the value you entered.")
        measured = rules.measure_elapsed(run.started_at)          # None if unstamped
        if rules.classify_claim(elapsed_seconds, measured) is rules.ClaimVerdict.IMPOSSIBLE:
            raise ValueError(rules.describe_claim(elapsed_seconds, measured))
        run = await self.run_repository.update(
            run,
            ...
            measured_seconds=measured,
```

> **Keep the two existing validations first, in this order.**
> `tests/test_column_guards.py::TestQualifierFinishTimeBound` monkeypatches
> `_require_own_active_run` to return a bare `object()` and asserts the
> "longer than a week" message. Reading `run.started_at` before that check turns
> that test into an `AttributeError`. The ordering above keeps it passing — and
> the ordering is also correct on its own terms: a nonsense value should be
> refused as nonsense, not as a discrepancy.

`rules.measure_elapsed(started_at)` is the third helper in T2.2: returns
`None` for a null `started_at`, otherwise `int((now(utc) - started_at).total_seconds())`
clamped at zero, normalising a naive datetime to UTC the way the page's ticker
already does ([`qualifiers.py:163-172`](../../../pages/qualifiers.py#L163)).
Putting it in `rules` rather than inline is what lets the page and the service
agree; putting the *timezone* handling there once is what stops a fourth copy of
the naive-datetime dance.

`measured_seconds` is stored on **every** submit, including an `OK` one. The
point is the reviewer's card and the audit trail, not just the refusal — a
discrepancy that falls under the threshold is exactly what a reviewer should be
able to see.

Add `measured_seconds` to the audit details of
`AuditActions.ASYNC_QUALIFIER_RUN_SUBMITTED` beside `elapsed_seconds`. Leave the
hand-rolled `write_log` + `event_bus.publish` pair as it is — it is legacy,
`check_dry_regressions.py` counts net-new, and converting it is not this wave's
job.

### Tests

`tests/services/test_async_qualifier_service.py`:

```python
async def test_submit_stores_the_server_measured_duration(db)
async def test_submit_refuses_a_claim_longer_than_the_run_has_existed(db)
async def test_submit_accepts_an_implausible_claim_and_still_records_it(db)   # service does not block
async def test_submit_tolerates_a_run_with_no_started_at(db)                  # measured stays None
```

The second and third are the pair that matters: they encode the decision that
only the impossible is refused. Manipulate `started_at` by updating the run row
after `start_run` rather than by patching the clock — the existing tests in this
file build real runs and that stays readable.

---

## T2.4 — The page asks about the implausible

**File:** `pages/qualifiers.py`, `_render_active_run`'s `_submit`.

The page already knows both numbers: it computes the elapsed value every second
from `run.started_at`. So the prompt costs no round trip.

```python
                async def _submit() -> None:
                    try:
                        seconds = parse_hms(time_in.value)
                    except ValueError as e:
                        notify_error(e)
                        return
                    measured = measure_elapsed(run.started_at)
                    if classify_claim(seconds, measured) is ClaimVerdict.IMPLAUSIBLE:
                        _ask_about_drift(seconds, measured)
                        return
                    await _do_submit(seconds)
```

`_ask_about_drift` opens a `ConfirmationDialog` with
`tone='primary'` (this is not destructive), titled *"Is that the right time?"*:

> Your timer says **1:14:22**. You typed **0:14:22**.
>
> If you finished a while ago and are only submitting now, your time is fine —
> submit it. If you dropped a segment, go back and fix it.

Buttons: **Submit 0:14:22** / **Let me fix it** (the cancel). The confirm path
calls the same `_do_submit`, so there is exactly one submit implementation.

Extract the existing body of `_submit` into `_do_submit(seconds)` — the notify,
the refresh and the error handling all stay there unchanged.

**The `IMPOSSIBLE` case gets no dialog**: the service refuses it and
`notify_error` shows the sentence from `describe_claim`. Do not pre-empt it in
the page — one authority for the refusal, and the page's clock is the less
trustworthy of the two.

Presentation importing two pure predicates from
`application.services.async_qualifier.async_qualifier_rules` is the intended
shape (`enforce_architecture.py` forbids presentation → `application.repositories`,
not presentation → a service module). **Verify the hook accepts the import on
your first write**; if it does not, add a thin `AsyncQualifierService` passthrough
(`classify_submitted_time(run, claimed)`) and call that instead — do not
suppress the hook.

### Tests

Page-level unit coverage here is thin by nature; the classifier is tested in
T2.2 and the refusal in T2.3. What to add is one test that the page's submit path
routes through the classifier — assert `pages.qualifiers` imports
`classify_claim` — plus the browser verification below, which is the real check.

---

## T2.5 — The reviewer sees both numbers

**File:** `pages/admin_tabs/admin_qualifiers.py`, `_render_queue`.

The queue card gains, under the existing badge row:

```
Claimed 0:14:22   ·   Timed 1:14:22   ·   [drift 1:00:00]
Started 3:12 PM · Finished 4:27 PM (Jul 30)
```

- `Claimed` is `elapsed_seconds`, `Timed` is `measured_seconds`, both through
  `format_hms`; a null measurement renders `Timed —`.
- The **drift badge appears only when the verdict is `IMPLAUSIBLE`** (reuse
  `classify_claim` — the same threshold the runner was asked about, so the
  reviewer sees exactly the cases the runner confirmed) coloured `orange`.
- Timestamps via `format_eastern_display`, which the page already imports as
  `_fmt`.

`list_pending_review` needs no change — `measured_seconds` is a column on the
rows it already returns.

The note field, the permalink played and the runner's other runs are **wave 3**.
Resist rebuilding the card here; this task is three labels and a conditional
badge.

### Tests

There is no test harness for this admin tab (page tests in this repo are
top-level and sparse — `tests/test_equipment_labels_page.py` is the pattern). Add
one asserting the queue renders the measured value if it is cheap, otherwise say
you relied on the browser check, per the README's definition of done.

---

## T2.6 — REST, seed, docs

**REST.** Add `measured_seconds: Optional[int] = None` to
`AsyncQualifierRunResponse`
([`api/schemas/async_qualifiers.py:146`](../../../api/schemas/async_qualifiers.py#L146)).
`SubmitRunRequest` is unchanged — a client still submits only its claim, and the
new refusal reaches it as a 400 through the existing error route. Add an API test
that an impossible claim is refused with a 400 and a readable body, beside the
existing submit tests in `tests/api/test_async_qualifiers.py`.

If the MCP qualifier reads enumerate run fields explicitly
(`mcpserver/tools/competition.py`), add `measured_seconds` there too and update
`tests/mcp/test_mcp_catalogue.py` if it snapshots the field list. If they return
the model wholesale, nothing to do.

**Seed.** `scripts/seed_online.py::_seed_qualifiers` — give the existing pending
run a `measured_seconds` an hour above its `elapsed_seconds`, so the queue shows
a drift badge on `poetry run python scripts/seed_dev.py` with no manual setup.
Keep it idempotent; set the field where the run is created.

**Docs.**

- [`docs/reference/data-model.md`](../../reference/data-model.md) —
  `measured_seconds` on `AsyncQualifierRun`: what it measures, why it is an upper
  bound, why it does not replace `elapsed_seconds`, and that it is null for
  live-race and pre-existing runs.
- [`docs/features/online-tournaments.md`](../../features/online-tournaments.md) —
  the submit rule: an impossible claim is refused, an implausible one is
  confirmed by the runner, and the reviewer sees both numbers.
- [`docs/reference/rest-api.md`](../../reference/rest-api.md) — the new response
  field and the new 400.

---

## Wave 2 wrap-up

```bash
poetry run pytest
poetry run python scripts/seed_dev.py     # twice, and once against a fresh DB
```

A fresh-database run matters here: this wave adds a column and a dev DB carried
across sessions will not exercise the migration.

Then, in two browser contexts:

1. As `player_two`, start a run and immediately submit `1:00:00`. **Refused**,
   with a sentence naming both numbers. The run must still be in progress
   afterwards — a refused submit that terminates the run would be worse than the
   bug this wave fixes.
2. Update that run's `started_at` an hour into the past (psql, or wait — psql),
   then submit a time 15+ minutes under the clock. **Dialog.** Cancel → still in
   progress. Confirm → submitted.
3. Submit an ordinary time on another pool. **No dialog** — the prompt must not
   fire on the normal path, which is the whole risk of this wave.
4. As `staff_user`, open the Review Queue: claimed, timed, drift badge on the
   drifted run and none on the ordinary one, both timestamps present.

Suggested PR split: *"Record the server-measured duration of a qualifier run"*
(T2.1–T2.3, T2.6's REST) and *"Ask about a finish time the clock disagrees with"*
(T2.4, T2.5).
