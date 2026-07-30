# Async qualifier run UX — implementation plan

Close the findings in
[`docs/reviews/async-qualifier-run-ux.md`](../../reviews/async-qualifier-run-ux.md):
a competitor can end their qualifier attempt with one unconfirmed click, the
server times every run and then ignores its own measurement, and a rejection
reaches nobody with a reason. The run itself — the draw, the permalink, the
server-derived clock — is already right and this plan must not disturb it.

**Read this file completely before starting any task.** It carries the evidence,
the design decisions and the ground rules that the wave files do not repeat.

## Wave files

| Wave | File | Theme | Findings | Migration? |
|---|---|---|---|---|
| 1 | [wave-1-no-lost-runs.md](wave-1-no-lost-runs.md) | Confirm the irreversible click; make a typed time unambiguous | F1a, F3, F5a | no |
| 2 | [wave-2-measured-time.md](wave-2-measured-time.md) | Store the server's own measurement, use it, show it | F2, F5b | **yes** |
| 3 | [wave-3-reason-and-remedy.md](wave-3-reason-and-remedy.md) | A rejection that says why; a reattempt someone can spend | F1b, F4, F5c | no |
| 4 | [wave-4-say-what-it-means.md](wave-4-say-what-it-means.md) | Explain the score, the estimate, and why you cannot start | F6, F7 | no |

Waves 1–3 are the blocker/critical/major findings; **you can stop after wave 3**
and the audit's headline is closed. Wave 4 is the two minors plus the copy work
that makes the surface explicable.

Do not start wave N+1 until wave N is merged.

## The evidence this exists to fix

All measured against the seeded `Dev Async Qualifier` on the `default` tenant
(2 runs/pool, 1 reattempt, 3 pools) — see the review for the full tables.

- **Forfeit is one click.** No dialog, no undo. `forfeit_run`'s own docstring
  ([`async_qualifier_service.py:538`](../../../application/services/async_qualifier/async_qualifier_service.py#L538))
  says it is irreversible and blocks replay "unless a reattempt is spent" —
  and the word "reattempt" appears nowhere on the player page.
- **`reattempt_run` has no caller in `pages/`.** The service method exists
  ([`:555-587`](../../../application/services/async_qualifier/async_qualifier_service.py#L555)),
  the REST route exists
  ([`api/routers/async_qualifiers.py:307`](../../../api/routers/async_qualifiers.py#L307)),
  the admin dialog lets a community configure `Allowed reattempts` — and no web
  surface spends one. A community can grant a remedy nobody can reach.
- **The server measures every run and drops the measurement.** `start_run`
  stamps `started_at` inside the draw transaction and the page's ticker derives
  the clock from it; `submit_run` then validates the *claimed* seconds only
  against `0 < x ≤ MAX_RUN_SECONDS` (a week). A run the server timed at 14
  seconds accepted a claim of `0:00:02`.
- **`1:23` silently means 83 seconds.** `_parse_hms`
  ([`pages/qualifiers.py:36-53`](../../../pages/qualifiers.py#L36)) folds any
  1–3 parts into base 60, so the likeliest typo in a field labelled
  *Finish time (H:MM:SS)* submits a time 60× too fast. `99:99:99` is accepted
  and stored as `100:40:39`.
- **A rejection carries no reason to anyone.** Reject is one click, the queue
  never asks for a note, `review_run`'s `note` parameter
  ([`:617`](../../../application/services/async_qualifier/async_qualifier_service.py#L617))
  is not passed by the page, and the DM reads in full: *"Your qualifier run was
  rejected."*
- **The reviewer decides from four facts, three of them raw.** The queue card
  ([`admin_qualifiers.py:429-451`](../../../pages/admin_tabs/admin_qualifiers.py#L429))
  shows name, `362439s`, pool and an optional VoD link. No timestamps, no
  measured duration, no permalink, no note field, no view of the runner's other
  runs.

Two symptoms say this is a wiring problem rather than a missing feature: every
capability the fix needs already exists in the service and is already exposed
over REST, and the one piece of state the fix needs to *add* (the measured
duration) is already computed on every page load and thrown away.

## Design decisions

Fixed. **If a task seems to contradict one of these, the task is wrong — stop
and ask.**

- **The runner still claims the time; the server's clock is evidence, not
  authority.** The timer starts at the draw and includes reading the seed,
  pausing, and the gap before submitting, so *measured ≥ claimed* is the normal
  case and a plain "use the measured value" rule would be wrong. The measurement
  earns three jobs: reject the *impossible*, ask about the *implausible*, and
  sit on the reviewer's card. Nothing auto-corrects a submitted time.
- **Confirmation goes to the irreversible action, and only there.** Forfeit gets
  `ConfirmationDialog`; Submit does not (it is the happy path, and wave 2's
  discrepancy prompt already interrupts the case that needs interrupting). This
  is the [cross-cutting theme](../../reviews/README.md#cross-cutting-themes)
  the crew audit named — do not spend the budget twice.
- **`H:MM:SS` means `H:MM:SS`.** The strict parser rejects one- and two-segment
  input with a sentence naming the shape, rather than guessing. Tolerant parsing
  plus a warning was considered and rejected: it leaves the 60×-too-fast
  submission reachable, and F2's cross-check cannot catch it when the claim is
  *smaller* than measured, which is the legitimate direction.
- **A reason is required to reject, optional to approve.** Rejection is the
  branch that owes the runner an explanation. Notes are already runner-visible
  (`get_run_notes` explicitly permits the run's own owner), so showing them is
  not a disclosure change.
- **Two ways to spend a reattempt, both requiring a reason.** The runner spends
  their own allowance (`reattempt_run`, capped by `allowed_reattempts`); a
  reviewer grants one on a runner's behalf (`grant_reattempt`, wave 3) which
  **bypasses the cap** — it is the override for a mis-click or a bad seed, so
  charging it to the runner's allowance would defeat the point. Both void
  exactly one terminal run and both are audited under distinct actions.
- **No new feature flag.** This subsystem is already behind
  `FeatureFlag.ASYNC_QUALIFIERS`, whose spec declares
  `service_modules=('application/services/async_qualifier/',)`. Every new
  **public** service method in that package carries
  `@requires_feature(FeatureFlag.ASYNC_QUALIFIERS)` —
  `check_feature_flag_gating.py` enforces it and a missing decorator is the one
  way this plan could quietly un-gate the feature.
- **No change to the scoring maths.** F6 ("a score can move after you finish")
  is correct behaviour that is never explained; wave 4 explains it. Do not touch
  `async_qualifier_scoring.py`'s formulas or `recompute_par_and_scores`.
- **The draw and the clock are off limits.** `start_run`'s locked transaction,
  the fairness pick, and the `started_at`-derived ticker are what the audit
  found *working*. No task here changes them; wave 2 reads `started_at` and adds
  a column beside it.

## Ground rules

Everything in [CLAUDE.md](../../../CLAUDE.md) applies. The parts these tasks hit:

**Three-layer pattern.** Presentation (`pages/`) → Service
(`application/services/async_qualifier/`) → Repository → Models.
`enforce_architecture.py` blocks violations at write time. The pure rule helpers
in `async_qualifier_rules.py` and `async_qualifier_scoring.py` are the
established home for I/O-free predicates — wave 2 adds one there rather than
inventing a place.

**Tenant scoping.** Every read goes through the repositories, which are already
`scoped(...)`. No task here needs a new unscoped query; if one seems to, it is
wrong.

**Errors.** Services raise `ValueError` (user-facing) / `PermissionError`
(authorization). The player page currently calls `ui.notify(str(e), …)` by hand
in three places; route them through `notify_error` (`from theme.notify import
notify_error`) as you touch them — the admin page already does.

**Audit + events.** `AsyncQualifierService` carries two **legacy** hand-rolled
`write_log` + `event_bus.publish` pairs (`submit_run`, `review_run`).
`check_dry_regressions.py` counts *net-new* occurrences, so editing around them
does not block — but any **new** audit that also publishes must use
`AuditService.write_and_publish`. `EventType` is an external contract: add
members, never rename. New audit actions go on `AuditActions` as constants (a
string literal trips `check_audit_actions.py`), and `actor` is passed
unconditionally (`check_audit_actor.py`).

**NiceGUI.** `background_tasks.create`, never `asyncio.create_task`. The admin
page's documented pattern is sync `@ui.refreshable` views reading from `state`
with async loaders that restore the captured client (`with client:`) before
`.refresh()` — follow it; mutating handlers run straight from `on_click`.
`ConfirmationDialog` lives at `theme/dialog/confirmation_dialog.py`
(`message`, `on_confirm`, `confirm_text`, `tone`, `title`).

**Mobile.** Both qualifier tables already call `enable_mobile_grid`. A new
column needs its `field_slots` entry if it renders as anything but plain text,
and every new card/dialog is re-measured at 390×844.

**Dev seed.** `scripts/seed_online.py::_seed_qualifiers` creates one approved and
one pending run, plus a review note. Three waves here need states it does not
produce (rejected-with-note, forfeited, voided-by-reattempt, a claim/measured
discrepancy, a closed qualifier whose board is public). Extend it in the wave
that needs the state — a state the seed never creates is a state nobody reviews.
Keep it idempotent (`get_or_create`) and tenant-scoped like the rows around it.

**File length.** `check_file_length.py` advises over 800 lines.
`admin_qualifiers.py` is 496 and gains a tab and two dialogs in wave 3;
`async_qualifier_service.py` is 754 and gains one method. Extract before you
cross — the package already splits `_access` / `_rules` / `_config` / `_draw` /
`_scoring`, and the review queue is the obvious page-side extraction
(`pages/admin_tabs/admin_qualifiers/…`, the way `admin_brackets/` is split).

## Verification loop

```bash
bash scripts/setup_env.sh                      # once
nohup ./start.sh dev > /tmp/app.log 2>&1 &     # wait for "Application startup complete"
poetry run python scripts/seed_dev.py
```

Mock-Discord logins at `/t/default/login`: `player_two`, `player_three`
(runners), `staff_user` (a qualifier admin, so also the reviewer). The surfaces:

- `/t/default/qualifiers` → **Open** → the run surface, as `player_two`
- `/t/default/admin` → **Qualifiers** tab → **Manage** → **Review Queue**, as
  `staff_user`

**Drive both sides at once.** Every wave here changes what one person's action
tells another person; a single browser context cannot see that. Two contexts —
runner and reviewer — is how the audit found its headline, and it is how each of
these fixes gets confirmed. See the [`ui-validation`](../../development.md)
skill for the harness; multi-step flows need their own script that reuses its
login.

```bash
poetry run pytest                    # whole suite, parallel
poetry run pytest -n0 -k qualifier   # serial, for -s / pdb
scripts/ui_flag_sweep.sh             # flags-off sweep: the pages must stay gone
```

The flags-off sweep matters more than usual: two waves add service methods and
one adds a REST route inside a flagged subsystem.

## Definition of done for every task

1. Implemented in the files named, at the layer named.
2. `poetry run pytest` green.
3. The task's own tests exist **and fail without the change** — say so if a test
   cannot meet that bar and why.
4. The affected surfaces render at 1500px **and** 390×844, verified by
   screenshot, with no new console errors.
5. Where the task changes what a *second* person sees (a reason, a badge, a DM),
   that second view is verified too — including the `MOCK_DISCORD` log for a DM.
6. Docs named in the task updated.
7. Committed with a message describing the behaviour change, not the diff.

If a task turns out to be wrong or blocked, **finish the rest of its wave and
say explicitly what you left out and why.** Do not silently narrow scope.

## When this directory is finished

`docs/README.md`: *design records are not kept after they ship.* Delete each
wave file as its wave merges. When the last one lands:

- delete this directory and
  [`docs/reviews/async-qualifier-run-ux.md`](../../reviews/async-qualifier-run-ux.md);
- remove both rows from the "Work in flight" table in
  [`docs/README.md`](../../README.md) and the audit's row from
  [`docs/reviews/README.md`](../../reviews/README.md);
- fix the two cross-cutting-theme bullets in `docs/reviews/README.md` that cite
  `reattempt_run` and `review_run`'s `note` as unwired capabilities, and the one
  that cites forfeit as an unconfirmed destructive action — they will no longer
  be true;
- make sure the behaviour lives in the feature docs, principally
  [`docs/features/online-tournaments.md`](../../features/online-tournaments.md)
  (the run/review loop), [`docs/reference/data-model.md`](../../reference/data-model.md)
  (`measured_seconds`, the reattempt states) and
  [`docs/reference/rest-api.md`](../../reference/rest-api.md).

Git history holds the rationale.
