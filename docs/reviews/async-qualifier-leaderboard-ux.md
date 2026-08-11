# Async qualifier flow and leaderboard — evaluation

**Scope:** the whole async-qualifier lifecycle from an organiser's empty
qualifier to a scored board — Admin → Qualifiers
([`pages/admin_tabs/admin_qualifiers/`](../../pages/admin_tabs/admin_qualifiers/) — a single
`admin_qualifiers.py` when this was written; it was split into a package by wave 2)
and its Manage drill-down, the player surface
([`pages/qualifiers.py`](../../pages/qualifiers.py)), the eleven service modules
under [`application/services/async_qualifier/`](../../application/services/async_qualifier/),
the run-expiry worker, the live-race capture path, and the REST and MCP reads of
the same services. This is the **second** async-qualifier audit; the first
(recorded as shipped in [README.md](README.md)) covered the runner's submit and
reattempt surface and its seven findings are closed. Nothing here re-opens them.

**Method:** read the services and auth gates first, then drove the running app
in a headless browser against Postgres. Baseline fixtures from
`scripts/seed_dev.py`, plus a stress fixture of **500 players, 4 pools × 12
permalinks, and 6,260 runs** across approved, pending, rejected and forfeited at
realistic proportions, with par and scores computed by the real scoring
functions. A second pass ran **20 probes** against the live database for the
things a single browser pass cannot reach: concurrency, the expiry worker,
live-race capture, seed rolling, and permalink acceptance. Query counts come from
wrapping the Tortoise connection's `execute_query`; browser timings and DOM
measurements from Playwright; REST numbers from curl against `/api` with the
seeded bearer tokens. Every number below is measured. Anything not driven is
tagged `code-read`.

**Headline:** the scoring formulas are exact — 32 hand-computed assertions
against `compute_par` and `compute_score` all pass, including both clamps and the
105 cap boundary. So is the atomic draw, which held under real contention, and so
is the entire run-expiry subsystem. What is wrong sits in three layers wrapped
around that correct core: the **slot bookkeeping** the board derives from runs,
the **review path's** missing concurrency control, and the **absence of
pagination anywhere in the subsystem**, which puts a 151,000-pixel page in front
of a moderator with 3,129 runs to work through.

---

## The measured shape of the flow

Server time on one qualifier — 3,128 runs, 500 entrants, single worker:

| Read | Time | Queries | Note |
|---|---:|---:|---|
| Admin `load_detail()` — six reads | **515 ms** | 38 | re-runs in full after *every* mutation |
| `list_runs` (admin Runs tab) | 176 ms | 9 | 3,128 rows hydrated |
| `get_leaderboard` | 170 ms | 7 | 3,031 rows hydrated to use 2,384 |
| `_other_runs_summary` (pure Python) | 72 ms | 0 | O(pending × all runs) |
| `get_run_availability` | 33 ms | 22 | ~5.5 queries per pool |

Wall clock in the browser, what a moderator waits for:

| Action | Time |
|---|---:|
| Switch to the Runs tab | **7.06 s** |
| Approve one run | **6.08 s** |
| Open the Manage drill-down | 4.40 s |
| Switch to the Review Queue | 3.53 s |
| Player's closed-qualifier page | 2.50 s |

232 runs were pending. At six seconds a verdict — plus a tab re-selection after
each one, because the refreshable resets — clearing that queue is about
**23 minutes of waiting**.

DOM handed to the browser. No table in this subsystem paginates:

| Surface | Rows/cards | Page height | DOM nodes |
|---|---:|---:|---:|
| Admin · Runs tab | 3,129 | **151,156 px** | 43,714 |
| Admin · Review Queue | 234 | 54,030 px | 5,262 |
| Player · Leaderboard | 505 | 24,826 px | 3,206 |
| Admin · Pools tab | 48 links | 3,048 px | 665 |

The tab strip sits at the top of that 151,000-pixel page. The automation driving
this audit could not click through to the Leaderboard tab after the Runs tab
rendered, because the control had scrolled a hundred and fifty metres out of
reach. A moderator has the same problem.

---

## Findings

### F1 · Nothing in the subsystem paginates — *shipped*

All four `ui.table`s are constructed without `pagination=`, so
`customize_table` reads `page_size` as `0` — which Quasar treats as "all rows" —
and sets `hide-pagination`, removing even the footer that would offer a page
size. The reports and the match/user/tournament family tables all pass
`pagination=25`
([`theme/tables/match.py:406`](../../theme/tables/match.py)); the qualifier
tables are the outlier. Measured above. The review queue is cards rather than a
table and needs its own bound.

### F2 · The leaderboard read hydrates a fifth of its rows to discard them — *shipped*

`get_leaderboard` calls `list_valid_for_qualifier`, which filters only on
`reattempted=False` and prefetches `user` and `permalink__pool` for every row.
The status and review filters are then applied in Python. Measured: **3,031 rows
hydrated, 2,384 used, 21% discarded after loading**, each survivor contributing
four scalars.

Two alternatives were run against the same data and verified to reproduce all
499 entries with matching totals, entry by entry:

| Implementation | Time |
|---|---:|
| As shipped | 170 ms |
| `.values()` with the filters in SQL, same Python maths | **18.5 ms** |
| Window-function aggregate, scoring in SQL | 10.5 ms |

Only `('qualifier', 'review_status')` is indexed today; the leaderboard's filter
is `(qualifier, reattempted, status, review_status)`.

### F3 · The drill-down reloads everything after every verdict — *shipped*

`load_detail()` fetches the qualifier, its pools, the review queue, *every* run,
the leaderboard, every preset and every live race — sequentially — then
`detail_view.refresh()` rebuilds the whole tab set. Every approval, rejection,
grant, pool edit and permalink paste runs all of it. Because the refreshable
rebuilds, the tab panel resets to Pools, so a reviewer is thrown out of the queue
after each verdict and must scroll back up a 54,000-pixel page to re-enter it.
Confirmed in the browser: after approving, the page read `Add Pool`.

### F4 · Four ways the board misreports, and a fifth found under probe — *shipped*

The formulas are right; the slot bookkeeping around them is not.

**F4a — live-race pools are counted as slots.** On the seeded
`Dev Async Qualifier`, one of three pools holds only live-race permalinks. The
board reports `slots 1/6` and `estimate 600.00`; a self-paced runner can only
ever fill **4**, making the honest estimate 400. `get_run_availability` already
excludes such pools — and
`test_availability_ignores_a_live_race_only_pool` pins that behaviour —
but `get_leaderboard` passes every pool id from `list_for_qualifier` straight
through.

**F4b — forfeits leave no trace.** A forfeit is written
`FORFEIT / APPROVED / score 0`, and the board's filter requires `FINISHED`, so
the run vanishes. `actual` is unaffected because the slot reads as unfilled, but
`estimate` then projects the player's good-run average across a slot they can
never refill. Someone who forfeited half their runs shows the same estimate as
someone who has not started. The same filter excludes live-race DNF and DQ runs,
which are written the same shape.

**F4c — ties get distinct ranks.** Rank is an `enumerate` index in
[`pages/qualifiers.py`](../../pages/qualifiers.py),
[`admin_qualifiers/page.py`](../../pages/admin_tabs/admin_qualifiers/page.py) *and*
[`mcpserver/tools/competition.py`](../../mcpserver/tools/competition.py) — three
independent derivations — while `LeaderboardEntryResponse` has no `rank` field at
all, forcing every REST consumer to invent a fourth. A three-way tie on 100.00
renders 1, 2, 3, ordered alphabetically because that is the input sort. For a
board that seeds a bracket, alphabetical order is deciding placements.

**F4d — zero-score entrants disappear.** A player whose every run forfeited or
was rejected is absent from the board rather than ranked last on 0.

**F4e — a rejected or voided run keeps the score it held while approved.**
`review_run` flips the status and then recomputes par over the approved set,
which no longer contains this run, so it is never rescored. Measured: a run
approved at `score 100.0` read `rejected · score 100.0` afterwards; a run voided
by a reattempt kept `score 103.31`. The board is right, because it filters on
approved. The runner's own table is not — it renders "rejected" beside a score —
and neither is the API: `GET /{id}/runs` returned **12 voided runs still carrying
a score**.

### F5 · Review has no concurrency control, and the claim is decorative

`online-tournaments.md` and the service docstring both state that runs are
claim-locked so two reviewers cannot double-handle one. `claim_run` and
`release_claim` exist and are exposed over REST. `review_run` never reads
`review_claimed_by`, and the web UI has no control that claims anything — the
browser showed **232 Approve buttons and 0 Claim controls**, so the "claimed"
badge the queue renders can never light up for a browser user.

Driven, not reasoned about:

- **Two reviewers, one run, simultaneously.** Both calls succeeded. Final state
  `approved`, `reviewed_by` the first reviewer, and *both* notes attached:
  `['rejected by B', 'approved by A']`. Since the player's table shows the most
  recent note, it can display a rejection reason on an approved run.
- **The runner received two DMs** — "…was approved. Reason: approved by A" and
  "…was rejected. Reason: rejected by B" — seconds apart, with no way to tell
  which is current.
- **Claim then review as someone else** — reviewed anyway, with the claim held.
- **Re-review** — an approved run at `score 100.0` flipped to `rejected` on a
  second call, with a fresh DM and no override record. `review_run` checks
  `status != FINISHED` but never `review_status`.

### F6 · One ungated read, and a guardrail that cannot see it

`get_leaderboard`
([`async_qualifier_reads.py:165`](../../application/services/async_qualifier/async_qualifier_reads.py))
is the only public read in the subsystem without
`@requires_feature(FeatureFlag.ASYNC_QUALIFIERS)`. With the flag forced off on
the `default` tenant it returned **499 entries** while `list_open_qualifiers`
raised `FeatureDisabledError`.

Today's callers are all gated at their own boundary — the page decorator, the
REST router's mount dependency, the MCP registration — so nothing leaks now.
That is precisely the situation the two-obligations rule exists to survive: the
next caller added will not be. `.claude/scripts/check_feature_flag_gating.py`
passes because it asks whether **any** method in the declared modules guards the
flag.

`AsyncQualifierLiveRaceService.mark_in_progress` is a second instance — a
mutation without the decorator its siblings carry.

### F7 · Par is exactly solvable from a runner's own score

The lockdown hides pools, pars and the board while a qualifier is open, on the
stated grounds that publishing them would tell a player who has not run yet
exactly what time they need. My-runs shows that player their own **Score** during
the window, and score is `(2 − elapsed/par) × 100`. One line of algebra recovers
par. Measured on the real fixture: `elapsed 5,400 s · score 100.00 → solved par
5,400 s`, against an actual `par_time` of 5,400 s.

`GET /{id}/me/runs` returns `AsyncQualifierRunResponse` with an unconditional
exact `score`, so fixing only the web page moves the leak one API call away.

### F8 · The run surface withholds information it already holds

The surface itself is well built — the reveal-equals-start card, the ticking
clock, the `H:MM:SS` echo ("Submitting 1:23:45 — 1 hour, 23 minutes, 45
seconds"), the forfeit confirmation naming its consequences and the reattempt
dialog gated on a typed reason all behaved as documented when driven. What is
missing is information the page has:

- **No deadline.** Runs auto-forfeit after 12 hours by default. Grepping both
  pages for `deadline` and `expir` returns **zero hits** — the card counts up
  with no hint a countdown exists, and the runner's only warning is a DM an hour
  out.
- **No seed on the record.** My-runs never shows which permalink was played, so a
  runner disputing a verdict cannot cite the seed. The reviewer's card shows it.
- **A granted void gives no reason.** The pool column reads "(reattempted)". The
  reason lives in `reattempt_reason` and goes out by DM but never appears on the
  page the runner returns to.
- **`expired_at` is read by neither page** (0 references), so an automatic
  forfeit is indistinguishable on screen from a chosen one — the exact
  distinction the column was added to make.
- **Raw enum values on screen** — `in_progress`, `finished`, `approved` in both
  tables — and an in-progress run renders "pending" in its Review column.

### F9 · The reviewer roster and the queue signal are both unreachable

`add_admin`, `remove_admin` and `list_admins` exist on the service and over
REST; no control anywhere in the admin page calls them, so a qualifier's reviewer
set can only be edited with an API token, while tournament admins are editable
from the user dialog. This is the *capabilities nobody wired* theme in
[README.md](README.md#cross-cutting-themes), recurring in the same subsystem
that supplied two of its earlier examples.

Nothing tells a moderator a run is waiting either. `submit_run` audits and
publishes an event; no DM or notification reaches the reviewer set. The queue is
pull-only, and the only way to discover work is to open a 4.4-second drill-down.

### F10 · The live-race capture path has three defects — *shipped, bar the reconcile control*

Live races are the second path that writes a scored, approved run, and it
bypasses review by design. The design is sound and was confirmed: still-racing
entrants are refused ("record again once the race finishes"), outcomes map
correctly (2 finishers scored off a par of 3,800 s, DNF → forfeit and DQ →
disqualified both zeroed), and par recomputes. Three things around it are not.

**F10a — `runs_per_pool` is never checked.** It is enforced only in `start_run`
([`async_qualifier_service.py:486`](../../application/services/async_qualifier/async_qualifier_service.py)).
One racer put in two live races in a `runs_per_pool=1` pool ended up holding
**2 runs**; `build_leaderboard` caps the pool at one slot, so the second is
dropped silently at scoring time. The racer ran a race that could never count and
nothing told them.

**F10b — "(assign later)" produces unscoreable runs.** The New Live Race dialog
offers a null permalink and `record_finish` captures against it without
complaint: two finishers written `permalink_id=None · score=None`, the par
recompute skipped, and both **absent from the leaderboard** with nothing
explaining why.

**F10c — a cancelled room strands the race.** The handler's `CANCELLED` branch
([`race_room_service.py:~410`](../../application/services/race_room_service.py))
updates the `RacetimeRoom` and leaves the `AsyncQualifierLiveRace` untouched, so
it sits at scheduled or in-progress forever. There is no manual
record-or-reconcile control in the admin page or in REST — `record_finish` is
reachable only from the inbound racetime FINISHED event — so a missed event has
no remedy.

Two smaller ones: `started_at` is stamped at record time, so every live-race run
shows `Started == Finished` and a blank Timed column; and an entrant with no
linked `User` is recorded in the audit detail only, with no surface listing
unmatched handles for staff to fix.

### F11 · Query patterns that will bite again as a qualifier grows

- `_pool_usage` issues about 5.5 queries per pool — **22 for four pools** —
  because `draw_candidates`, `async_seed_count` and the per-pool count each go to
  the database separately, and the first two re-read the same permalink list.
- `valid_run_counts_by_permalink_for_pool` pulls every run's `permalink_id` in a
  pool and tallies in Python where a `GROUP BY` would do.
- `_count_reattempts` calls `list_for_user`, which prefetches `permalink__pool`
  and `review_notes__author`, purely to count rows matching two booleans.
- `recompute_par_and_scores` issues one UPDATE per approved run on the permalink,
  outside any transaction, and re-reads pool and qualifier on every call. A
  failure part-way leaves a fresh par beside stale scores.

### F12 · How seeds get into a pool

Rolling works: a preset-tied pool created through the UI rolled three ALTTPR
seeds with provenance recorded, and a dk64r preset was refused with the right
message. The edges are the problem.

- **No URL validation anywhere.** `add_permalink`, `add_permalinks_bulk` and
  `update_permalink` strip whitespace and store what is left. Pasting seven lines
  accepted five, including `not-a-url-at-all`, `ftp://weird/x` and
  `javascript:alert(1)`, each then rendered as a clickable link. The everyday
  cost is worse than the exotic one: because reveal equals start, a runner drawn a
  typo'd permalink has already spent their slot on a seed that will not open.
- **Roll is offered where it cannot work.** The button renders whenever
  `pool.preset` is set, with no reference to `ASYNC_RANDOMIZERS` in the page at
  all. The refusal only arrives after clicking, in a dialog that has a count field
  and nothing else — it cannot change the preset, so the only exit is Cancel.
- **The count field's max is decorative.** `ui.number(min=1, max=25)` keeps the
  value 40 when 40 is typed. The service refuses it correctly.
- **Rolls are serial.** `roll_permalinks` loops up to 25 `generate_seed_call`s one
  after another inside the request — instant under `MOCK_SEEDGEN`, minutes for a
  real randomizer, with no progress and no cancellation. `code-read` for the
  real-randomizer case.
- **No per-permalink controls.** Delete one seed, edit its URL, toggle its
  live-race flag — all three exist on the service and over REST, none is reachable
  from the page, so a single bad seed can only be fixed by deleting the pool.

### F13 · The API's unbounded reads and missing rank

`GET /async-qualifiers/{id}/runs` returns all **3,129 runs in one 1.66 MB
response** (0.27 s). The leaderboard endpoint is a bare 499-element array
(57 KB, 0.19 s) with **no `rank` field** — the fourth place rank has to be
inferred, per F4c.

Authorization and isolation are sound and were probed: 401 with no token, 404 for
a bogus id, 403 on writes with the read-only token, and **404 on all four
cross-tenant reads** (`{id}`, `/leaderboard`, `/pools`, `/runs` with the
`second`-tenant token).

### F14 · Qualifier lifecycle events are never published

Four `EventType` members cover run submitted, reviewed, expired and live-race
recorded. Nothing publishes when a qualifier is created, opened, updated, closed
or deleted; when a pool or permalink changes; or when a run is forfeited or
reattempted. Those paths audit correctly, so the trail is there, but a webhook
subscriber cannot learn that its qualifier just opened — the announcement a
Discord integration would most want to make.

---

## What held up

Worth recording, because several are the parts most likely to be wrong.

**The atomic draw held under real contention.** Two simultaneous `start_run`
calls for one player produced exactly one run, the second refused with "You
already have a run in progress"; four concurrent draws for four players all
opened with a permalink assigned. That is the guarantee the whole
reveal-equals-start design rests on.

**The entire expiry subsystem came out clean.** It warned once at the configured
lead time, stayed idempotent across ticks (`expiry_warned_at` unchanged), then
forfeited with `expired_at` and `measured_seconds` both stamped and the slot
correctly spent. All four runner DMs render, carry link buttons, and the expiring
one uses Discord's own `<t:…>` markup so each recipient reads the deadline on
their own clock. The expired DM names the remedy — ask an organiser for a grant —
which is the call to action that situation owes.

**Also confirmed:** the seven availability reasons each produce their own
sentence; the forfeit confirmation names its consequences and offers the
remaining reattempt without calling it an undo; rejection refuses a blank reason
at both the button and the service while approval correctly does not; self-review
is blocked; the lockdown hid the board on the open qualifier and revealed it on
the closed one; mobile at 470 px produced grid cards rather than an overflowing
table; no console errors on any surface.

**Test coverage.** The 12 existing `build_leaderboard` and par/score unit tests
are sound. Nothing in the suite covered claim collision, concurrent verdicts,
re-review, stale scores after a rejection, tie ranks, live-race pools in
`slots_total`, `runs_per_pool` in a live race, or the leaderboard's feature gate
— every place this audit found a problem. Those are now
`tests/services/test_async_qualifier_audit_findings.py`, written as failing
tests against the current behaviour so each fix has a target.

---

## Decisions taken

Four questions in this audit were policy rather than defect, and were settled
with the maintainer:

| Question | Decision |
|---|---|
| A slot spent on a forfeit/rejection the player cannot refill | **Counts as a realised zero.** `slots_filled` means slots consumed; `estimate` projects only slots still runnable. This moves rankings on Estimate. |
| Score visible to a runner mid-window (F7) | **Coarsen to three bands** — under / near / above par. Noted at the time: the "under par" band still tells a fast runner that par is above their time, which is a real bound for exactly the players the lockdown targets. Accepted. |
| A racer exceeding `runs_per_pool` in a live race (F10a) | **Record it as voided** — `reattempted=True` with a reason, so the run exists in history, shows as voided on the racer's own table, and never touches par or scoring. |
| Live-race and self-paced runs on one board | **One board**, with the slot counting fixed per F4a. |

---

## Remediation order

Ordered by leverage, which is the argument: each buys more than the one below it
per hour spent.

| Wave | Findings | Status |
|---|---|---|
| 1 | F1, F2 | **Shipped.** Pagination and the projected leaderboard read. |
| 2 | F3 | **Shipped.** The moderator loop — per-tab loaders and a preserved tab. |
| 3 | F4, F10 | **Shipped**, bar F10's reconcile control (see below). What the board counts, and the live-race path. |
| 4 | F5, F6 | Open. Review integrity and the flag hole. |
| 5 | F7, F8, F9 | Open. The information both sides are missing. |
| 6 | F11, F12, F13, F14, F10's reconcile control | Open. Query fat, seed authoring, the API's unbounded runs read, events. |

### What wave 3 changed, measured

| Measure | Before | After |
|---|---|---|
| `Dev Async Qualifier` board, one live-only pool of three | `slots 1/6`, `estimate 600.00` | **`slots 2/4`, `estimate 200.00`** |
| Stress board entries | 499 | **500** (F4d: the entrant who only forfeited) |
| Entrants with every slot spent whose `estimate` exceeded `actual` | 26 of 26 | **0 of 26** |
| Shared ranks on a 500-player board | none — ties rendered 1, 2, 3 | **5 ties share a rank, and the next skips** |
| Rejected or voided runs carrying a stale score | 22 in the dev database | **0** (cleared going forward, plus migration 68's backfill) |
| `get_leaderboard` on 500 players | 21 ms | 44 ms — it now reads spent slots too, still 4× better than the 170 ms it started at |

**Deferred, with the reason.** F10's manual record-and-reconcile control and its
unmatched-handle list are the half of that finding that needs racetime transport
work `MOCK_RACETIME` cannot exercise, so they moved to wave 6 rather than shipping
unverified. Everything else in F10 is in: the cap check, the null-permalink refusal,
and the cancelled-room transition.

### What waves 1 and 2 measured, after

Same fixtures, same script, same machine as the numbers above.

| Measure | Before | After |
|---|---:|---:|
| `get_leaderboard` server time | 170 ms | **21 ms** |
| Open the Manage drill-down | 4.40 s | **1.45 s** |
| Switch to the Review Queue | 3.53 s | **1.47 s** |
| Approve one run | 6.08 s | **2.53 s** |
| Switch to the Runs tab | 7.06 s | **2.08 s** |
| Switch to the Leaderboard tab | *unreachable* | **2.04 s** |
| Runs tab: rows / height / DOM nodes | 3,129 / 151,156 px / 43,714 | **25 / 1,672 px / 817** |
| Review Queue: cards / height | 234 / 54,030 px | **20 / 5,588 px** |
| Player board: rows / height / nodes | 505 / 24,826 px / 3,206 | **50 / 1,632 px / 569** |
| Reviewer keeps their tab after a verdict | no | **yes** |

The board is byte-identical to the one it replaced — all 499 entries, matching
totals, checked entry by entry. The Leaderboard tab row is the one worth reading
twice: it had no "before" because the tab strip sat above a 151,000-pixel page and
could not be clicked at all.

F13's unbounded `GET /{id}/runs` moved to wave 6 rather than shipping with F1: the
web fix is client-side paging over rows already loaded, which is the pattern this
repo chose deliberately, while the API needs a real page parameter and a schema
change.

Delete this file once the remaining findings ship — the feature docs become the truth
and git history keeps the rationale.

## Reproducing any of this

Postgres 16, the app booted with `./start.sh validate`,
`poetry run python scripts/seed_dev.py`, then a stress fixture adding 500 players
with tenant memberships, two qualifiers of 4 pools × 12 permalinks, and 6,260
runs. Five probe scripts covered concurrency (5 cases), stale scores and expiry
(7 cases), live-race capture (6 cases), seed rolling driven through the browser,
and permalink acceptance; each built a throwaway qualifier and removed it
afterwards. REST numbers used the seeded bearer tokens documented in the
[`api-validation`](../development.md) skill.
