# SGL26 onsite gaps — implementation plan

Three features asked for at SpeedGaming Live 2025 that the app still does not
do. They are independent of each other and can be built in any order, but they
share one deadline: **the app freezes at the end of September 2026** for manual
testing before the 22–25 October event.

**Read this file completely before starting any plan.** It carries the evidence,
the decisions and the ground rules the three plan files do not repeat.

## The plans

| # | File | What it closes | Flag? | Migration? |
|---|---|---|---|---|
| 1 | [1-stage-notifications.md](1-stage-notifications.md) | Assigning a stage tells nobody, and nothing reminds a runner before their broadcast match | no | yes (2 columns) |
| 2 | [2-volunteer-hours.md](2-volunteer-hours.md) | Nothing totals a volunteer's hours against the badge-comp tiers | no (inside `VOLUNTEERS`) | **no** |
| 3 | [3-payouts.md](3-payouts.md) | Prize splits and Matcherino handles live in Discord threads and a private spreadsheet | **yes, new** | yes (1 model, 3 columns) |

Suggested order is the table order: plan 1 is two columns and a worker, plan 2
adds no model at all, plan 3 is the only one carrying a new flag, a leak test
and seed rows. Nothing forces that order.

## The evidence this exists to fix

From the SpeedGaming Live Discord, read 2026-08-02. Feedback lives in the
`#onsite-tool` forum, opened by Synack on 2025-10-23 and still largely open.

**Nobody tells a runner they are on stage.** incoherent, `#onsite-tool`,
2025-10-30: *"The onsite schedule shows which matches are on stage, but it
doesn't tell the runners itself (someone has to tell you out of band, or you
have to be looking at the schedule at the right time). Maybe the tool could send
a Discord DM 15-30m ahead of time to tell you 'hey you're on stream, go to X
stage instead of the tournament room'."*

Confirmed in the code: `MatchService.assign_stage` audits, publishes
`MATCH_STAGE_ASSIGNED` and calls `match_live.publish`, and sends no DM at all.
The scheduled-match DM carries a stage name, but only when the stage was already
set at scheduling time, which for a broadcast match it usually is not. There is
no pre-match reminder worker anywhere in the app; `volunteer_reminder` is the
only reminder loop that exists.

**Payouts are a Discord thread and a private spreadsheet.** adirondackrick to
every tournament admin, 2025-10-30: *"In your tournament admin thread, can you
please post the following information: Place, Runner's Name (Matcherino ID if
different), % of prize pool won, $ amount."* Hurfydurfy's reply for ALTTPR is the
canonical shape, and its arithmetic fixes a design question:

```
Total prize pool (taken from sglive.speedgaming.org): $1000
Bonus: $100

1st place - Jem (Jem041#578236):            50% / $550
2nd place - ninjembro (Cody_Allyn#1102083): 30% / $330
3rd place - Specks (SpeckySpecks#1323840):  10% / $110
3rd place - Andy (Andy#86139):              10% / $110
```

$550 is 50% of $1100, so **the bonus folds into the pool before percentages
apply**. Two rows share place 3, so **ties are the normal case, not an edge
case**. Star1468, 2025-10-14: *"I have Matcherino info saved, and I just keep a
Google sheet with a list"* — the handles are stable across years and belong on
the person, not on the payout. Jam, 2025-10-30: *"Totals on the sgl site do not
include the bonuses."* Star1468, 2025-10-16: the in-person leaderboard was
*"out of date by....at least a week or two"* because only two people can edit it.

Nothing in the codebase matches `payout`, `prize` or `matcherino`.

**Volunteer hours are counted by eye.** Dani3883 announces the policy
(`#announcements`, 2026-08-01): *"Anyone who volunteers for a minimum of 8 hours
will have their SGLive 2026 badge comped. Additional incentives for those
volunteering for 12 or 16+ hours."* Intake is a Google Form, the schedule is a
Google Sheet, and *"what departments are we most lacking?"* was answered on
2026-08-01 with *"At a quick glance (on mobile)"* plus a spreadsheet link.

`DEFAULT_MAX_HOURS = 8.0` exists in `volunteer_autoschedule_service.py`, but it
is a **cap on what the autoscheduler will assign**, not a total of what someone
served. No code sums a volunteer's hours.

**What is already closed, and must not be rebuilt.** Checked against the tree on
2026-08-02: player reschedule requests, per-tournament notification
subscriptions with crew buttons (`TournamentNotificationPreference`), automatic
dark mode (`ui.dark_mode(None)` follows the client theme), per-viewer timezones,
Challonge linking, native brackets with static spectator views, tournament-scoped
Discord role grants, seat draw at check-in, equipment lending, and the
coordinator DM when a volunteer releases a shift. Several of these answer
`#onsite-tool` threads that still read as open.

## Design decisions

Fixed, and agreed with the product owner before these files were written.
**If a task seems to contradict one of these, the task is wrong — stop and ask.**

- **The stage reminder gets its own per-tournament column.**
  `room_open_minutes_before` already means "how early to open a racetime room"
  and is read by `race_room_service.py`; overloading it would couple two
  unrelated behaviours. It is a per-*tournament* column rather than a per-tenant
  `SystemConfiguration` (the shape `volunteer_reminder_lead_minutes` uses)
  because a Best-of-NES stage call and an OOTR stage call are not the same
  problem.
- **Clearing a stage sends its own DM and re-arms the reminder.** Telling
  someone they are on Kraid and never retracting it is the failure this feature
  exists to prevent.
- **Payout amounts are computed, never stored.** A row is a place and a
  percentage; the money is `(pool + bonus) × percentage` at read time. Storing
  it would create a second source of truth that drifts the moment the pool moves,
  which it does throughout the event.
- **Ties are first-class.** Two payout rows may share a `place`. No even-split
  arithmetic hidden from the admin checking the numbers.
- **The Matcherino handle lives on `User`, is not unique, and is labelled
  unverified.** The Challonge, Twitch and racetime links are unique because a
  provider verified them. This one is typed by hand, and a typo under a unique
  constraint would lock the rightful owner out of their own handle.
- **Volunteer hours are the union of covered time, not the sum of durations.**
  A coordinator can hand-assign overlapping shifts, and 8am–12pm plus 10am–2pm
  is six hours served, not eight. There is no interval-merge helper in the
  codebase today (`volunteer_autoschedule_service._overlaps` is a boolean), so
  this is new code.
- **Volunteer hours count published assignments.** A draft is
  `auto_generated=True`, flipped to `False` by `publish`; `release` **deletes**
  the row rather than flagging it, so "not withdrawn" needs no predicate.
  Acknowledgement is not required — someone who turned up but ignored the DM
  still served the hours.
- **Only payouts gets a flag.** Prize money is SpeedGaming-shaped and most
  communities will never pay anyone. Volunteer hours sit inside the existing
  `VOLUNTEERS` flag, whose spec already declares the whole
  `application/services/volunteer/` package. Stage notifications are a
  notification on a surface every community uses.

## Ground rules

Everything in [CLAUDE.md](../../../CLAUDE.md) applies. The parts these plans hit:

**Three-layer pattern.** Presentation (`pages/`, `theme/`) → Service
(`application/services/`) → Repository (`application/repositories/`) → Models.
`enforce_architecture.py` blocks violations at write time, and classifies
`api/`, `discordbot/` and `mcpserver/` as presentation: they call services and
must not import repositories.

**Tenant scoping.** Repositories read via `scoped(...)` and write with
`tenant_id=current_tenant_id()`; most new ones should subclass
`TenantScopedRepository` (`application/repositories/_base.py`). A cross-tenant
query is allowed only where a worker needs one, and its docstring must say so —
see `VolunteerAssignmentRepository.due_for_reminder` for the sanctioned shape.
Any worker touching scoped data wraps it in `tenant_scope(tenant_id)`;
`for_each_tenant_scoped` in `application/utils/background_loop.py` does this for
a batch.

**Audit and events.** `AuditService.write_and_publish` for the pair;
`check_dry_regressions.py` blocks a hand-rolled `write_log` +
`event_bus.publish` sequence. `EventType` is an external contract — add members
and add them to `EventType.ALL`, never rename. Where a plan deliberately adds
*no* event (the two reminder/read cases), the service docstring says so, because
silence otherwise reads as an oversight.

**Errors.** Services raise `ValueError` for user-facing problems and
`PermissionError` for authorization; `require_found(obj, label)` for a missing
entity. Presentation catches and notifies. `FeatureDisabledError` is a
`NotFoundError`, so a disabled flag 404s over REST and notifies in the UI.

**Feature flags are two obligations.** Hiding a tab is not gating. A flagged
subsystem needs `@requires_feature` on the owning service's public entry
methods *and* the entry-surface guards, and it must declare its
`service_modules` in its `FeatureFlagSpec`. `check_feature_flag_gating.py`
enforces both halves; `tests/test_feature_flags.py` fails until registry parity
holds.

**Tables.** Every `ui.table` needs `enable_mobile_grid(...)` and a
`table_key=TableKeys.X`, both hook-enforced. `pages/admin_tabs/admin_webhooks.py`
is the closest working example of a CRUD tab that does both.

**NiceGUI.** `background_tasks.create`, never `asyncio.create_task`. Capture
`context.client` before a background task that calls `ui.notify`. Discord sends
from a request handler go through `discord_queue.enqueue`, not an awaited call.

**Timezones.** All datetimes stored UTC. Discord embeds get native
`<t:unix:F>` markup via `discord_embeds.time_field`, never a formatted string,
so each recipient's client localises it. A worker rendering for someone else
passes an explicit `tz`; it must never rely on the ambient viewer clock.

**Writing rules.** Every user-facing string in these plans — DM copy, notify
text, column headers, help text — follows the "Writing user-facing text" section
of CLAUDE.md. No banned words, no "**Bold term**: explanation" lists, one em
dash maximum per piece of prose.

**File length.** `check_file_length.py` advises over 800 lines.
`match_service.py` and `volunteer_schedule_service.py` are both already large —
check before adding, and extract a module the way
`application/services/match/match_review.py` already is.

## Verification loop

```bash
bash scripts/setup_env.sh                      # once
nohup ./start.sh dev > /tmp/app.log 2>&1 &     # wait for "Application startup complete"
poetry run python scripts/seed_dev.py
```

Mock-Discord logins at `/t/<slug>/login`: `staff_user`, `proctor_user`,
`player_one`…`player_four`. Pages live under `/t/default/…`; a bare `/admin`
404s. Chromium is at `/opt/pw-browsers` — **never run `playwright install`**.

Discord cannot be driven headlessly and `MOCK_DISCORD` never connects a bot, so
DM copy and embeds are verified by rendering the builders and reading them back
— use the `/discord-ux` skill, not a live client.

```bash
poetry run pytest                 # whole suite, parallel
poetry run pytest -n0 -k payout   # serial, for -s / pdb
scripts/ui_flag_sweep.sh          # flags-off sweep
```

## Definition of done for every task

1. Implemented in the files named, at the layer named.
2. `poetry run pytest` green.
3. The task's own tests exist **and fail without the change** — say so if a test
   cannot meet that bar and why.
4. Affected surfaces render at 1500px **and** 430px with no new console errors.
5. Docs named in the task updated.
6. Committed with a message describing the behaviour change, not the diff.

If a task turns out to be wrong or blocked, **finish the rest of its plan and
say explicitly what you left out and why.** Do not silently narrow scope.

## When this directory is finished

`docs/README.md`: *design records are not kept after they ship.* Delete each
plan file as it merges; when the last lands, delete this directory, remove its
row from the "Work in flight" table, and make sure the behaviour lives in the
permanent docs:

- [`docs/reference/data-model.md`](../../reference/data-model.md) — the payout
  model, and every new column.
- [`docs/reference/services.md`](../../reference/services.md) —
  `PayoutService`, `VolunteerHoursService`, the stage reminder worker.
- [`docs/features/discord.md`](../../features/discord.md) — the stage DMs and
  their link targets.
- [`docs/features/payouts.md`](../../features/payouts.md) — new, written as
  part of plan 3.
- [`docs/features/feature-flags.md`](../../features/feature-flags.md) — the
  `PAYOUTS` registry row.
- [`docs/current-state.md`](../../current-state.md) — capability table.

Git history holds the rationale.
