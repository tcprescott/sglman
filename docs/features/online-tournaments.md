# Online Tournaments

Wizzrobe began as an *on-site* restream tournament manager and also runs **online**
tournaments, succeeding [SahasrahBot](https://github.com/tcprescott/sahasrahbot).
The subsystems themselves are documented at the reference level —
[services](../reference/services.md), [data model](../reference/data-model.md),
[seed generation](../reference/seed-generation.md),
[REST API](../reference/rest-api.md). This page holds the cross-cutting decisions
that no single subsystem owns.

## Succession scope

The succession covers SahasrahBot's **tournament and racing mission only**, fixed at
five features: async qualifiers, seed rolling from user-authored presets, Discord
Events sync, SpeedGaming schedule ETL, and the racetime.gg room lifecycle.

Everything else retires with SahasrahBot or lives on a thin community bot Wizzrobe
does not absorb: per-tournament handler classes (replaced by user-definable config),
spoiler races, community dailies, ranked-choice voting, and general Discord
community features (reaction and voice roles, holy images, inquiries, `konot`).
SahasrahBot's dormant `Schedule*` models were a half-finished in-house scheduler —
the SpeedGaming ETL supersedes them; do not port them.

This is the standing answer to "shouldn't Wizzrobe also do X, SahasrahBot did?"

## Tournament logic is user-definable data, not code

A community defines tournament behaviour through the admin UI, with no code change
and no deploy. The buildable shape is declarative config selecting among a **finite
registry of named strategy primitives**, plus safe templated text (`{placeholder}`
substitution, never `eval`).

It is explicitly **not** a scripting engine or per-tenant plugin code — that would
relocate the code-per-tournament problem rather than solve it, and add a security
surface. A new *primitive* is a reviewed code change available to every tenant; a new
*tournament or qualifier* is pure config. The corollary: user-definable must not
drift into user-breakable. A need that config cannot express becomes a new named
strategy for everyone, never an escape hatch for one tenant.

The substrate is `Tournament.config` + `validate_tournament_config` +
the `tournament_strategies/` registry.

**Hybrid config split rule.** Knobs a background worker queries go in typed columns
(`opens_at`/`closes_at`, `racetime_auto_create_rooms`, `room_open_minutes_before`,
`require_racetime_link`, goal); templates, scoring parameters and strategy choices go
in the Pydantic-validated JSON `config` blob. The test is "can a worker's SQL scan
need to filter on it?", not preference — a worker-scanned value buried in JSON turns
a cheap indexed scan into a full-table deserialize.

## The autonomous actor is a real user row

Workers and bot handlers act as a seeded system `User` (sentinel `discord_id` +
`is_system`, via `UserService.get_system_user`) — **not** a `-1` sentinel with a null
audit actor, which is what sahabot2 used. The audit trail snapshots the actor and the
convention is to pass `actor: User` explicitly with no null branch, so an autonomous
path needs a genuine row. Tenant comes from `tenant_scope`, never from the actor.

## Two bot runtimes, opposite tenant-resolution models

`racetimebot/` and `discordbot/` look like peers and are structured as peers, but
they resolve tenants in opposite ways. **Do not generalize one onto the other.**

- **Racetime is 1:1.** A room belongs to exactly one tenant — the one whose match created it — so an inbound event resolves slug → room → tenant and runs inside that single `tenant_scope`.
- **Discord fans out.** `Tenant.discord_guild_id` is not unique, so one guild can back several tenants and an event must be considered for each linked tenant.

Copying the Discord fan-out shape into racetime leaks a sibling tenant's data;
copying racetime's isolation into Discord silently drops events.

**The shared-guild reconciler trap.** Because a guild can back several tenants,
"cancel every scheduled event in the guild that isn't in my schedule" would delete
another community's events. The reconciler's working set is only *this tenant's own*
`DiscordScheduledEvent` rows; a `discord_event_id` present in the guild but absent
from this tenant's link table belongs to someone else and is left untouched. Same
isolation `DiscordRoleMapping.tenant` already gives role sync.

## Migrating a community off SahasrahBot

These are one-way doors:

- Each community becomes a tenant and cuts over when the features **it** uses are live.
- SahasrahBot is also Tortoise/Aerich, so migration is a DB-to-DB backfill: verified racer links → `User.racetime_*`, presets and weightsets → `Preset`, async tournament history → `AsyncQualifier*`.
- **Never cut a qualifier mid-window** — drain it or migrate it whole.
- During a parallel run, exactly one bot owns a community's racing at a time. **Never two bots in one racetime room.** The racetime category identity transfers last.

## Naming

SahasrahBot's *Async Tournament* is Wizzrobe's **Async Qualifier**. The rename is
deliberate: the workflow (self-paced runs against a permalink pool inside a window)
shares nothing with a `Tournament`'s, and reusing the name would collide with the
existing `Tournament` aggregate and invite conditional behaviour in both.
`AsyncTournament*` in upstream source and old migrations maps 1:1 onto
`AsyncQualifier*`.

## Async qualifiers

The self-paced permalink-pool qualifier is a peer aggregate of `Tournament` with its
own state machine: **window opens → draw → run → review → scored leaderboard →
close**. Surface reference:
[`AsyncQualifierService`](../reference/services.md#async_qualifier_servicepy--asyncqualifierservice).

**Reveal == start.** A player draws a permalink and the run clock starts in the same
atomic, row-locked transaction — there is no "look at the seed, then decide". The
transaction is what enforces one active run per player, the `runs_per_pool` cap, and
permalink no-repeat.

**A permalink must be a link, and a paste says what it skipped.** Everything downstream
rests on the seed opening, and reveal being start means a mangled URL costs a *run*, not
a click: the slot is spent the moment it is handed over. So `add_permalink`,
`add_permalinks_bulk` and `update_permalink` all validate through
`rules.permalink_url_error` — http(s) with a host, deliberately no further, because a
permalink points at whichever randomizer site rolled it. The paste path skips a bad line
instead of failing the batch and returns `BulkPermalinkAdd(created, rejected)` with the
1-based input line and the reason; the dialog reports each one and keeps the refused
lines so the two that came across mangled can be fixed without re-finding the twenty
that did not. `POST /pools/{id}/permalinks/bulk` returns the same two lists.

**Rolling is offered only where it can work.** `roll_refusal` is shared between the page
and the service, so a pool whose preset belongs to an asynchronous randomizer says so on
the card rather than after the click — the roll dialog holds a count field and nothing
that could change the preset, so its only exit was Cancel. Rolls are serial and
synchronous (each seed is a call to the generator), which the dialog says out loud, and
the batch is capped at `MAX_ROLL_COUNT` (25) — enforced by the field as well as the
service, since `ui.number(max=…)` marks a field invalid and submits the value anyway.
One seed can be edited or removed on its own from the Pools tab.

**Imbalance-forcing fairness.** The draw picks a permalink at random, *unless* the
pool's play-count spread has crossed `draw_imbalance_threshold`, at which point it
forces the least-played one. Pure randomness leaves permalinks with wildly different
sample sizes, and par is a mean over the fastest runs — a thin permalink produces a
par (and therefore scores) nobody can trust. Forcing only past a threshold keeps the
common case unpredictable.

**Finish times are bounded, and typed as exactly `H:MM:SS`.** A submitted time must be
positive and under `MAX_RUN_SECONDS` (a week), so a typed-in typo is a readable
validation error rather than an out-of-range column write. The entry field is parsed by
[`application/utils/duration.py`](../reference/services.md#durationpy), which requires
all three segments: folding shorter input into base 60 made `1:23` mean 83 seconds — a
time 60× too fast that reads as correct everywhere afterwards. The field echoes what it
read (*"Submitting 1:23:45 — 1 hour, 23 minutes, 45 seconds"*) before the runner
commits.

**Forfeit is confirmed.** It is the one irreversible control on the run surface — the
run scores 0 and the pool slot is spent — so it opens a `ConfirmationDialog` naming
those consequences. Submit does not: it is the happy path.

**The server's clock is evidence, not authority.** `start_run` stamps `started_at`
inside the draw transaction, and submit records the wall clock since then as
`measured_seconds` beside the runner's claim. Because the timer keeps running while the
player reads the seed and gets around to submitting, measured is an upper bound and
*measured ≥ claimed* is the normal case — so the measurement gets three jobs and no
more: the service **refuses** a claim longer than the run has existed (past a two-minute
clock grace), the run surface **asks** about a claim 15+ minutes under the clock
("Your timer says 1:14:22. You typed 0:14:22.") without ever blocking it, and the
review queue **shows** both numbers with a drift badge on the ones the runner
confirmed. Nothing auto-corrects a submitted time.

**Review is adversarial by construction.** Reviewers are the qualifier's own `admins`,
runs are claim-locked so two reviewers cannot double-handle one, and **self-review is
blocked** — an admin who ran the qualifier cannot approve their own run. Live racetime
qualifier races are the deliberate exception: they skip sign-off entirely and are
written `APPROVED`, because a racetime result is self-attributing.

**The claim is a lock, and the verdict is a compare-and-set.** Three ways two
reviewers collide on one run, and what each gets:

| Collision | Outcome |
|---|---|
| One holds the claim | The other is refused **by name** ("Ana has claimed this run for review"). Claim/Release sit on the queue card, either reviewer may release, and the expiry worker sweeps a claim older than `REVIEW_CLAIM_TTL` (2h) so a closed tab cannot park a run |
| The run is already settled | Refused, unless the caller passes `override=True`. Reversing a verdict is legitimate; doing it indistinguishably from a first verdict is not |
| Both commit at once | `settle_review` writes only while the run still carries the status the reviewer read, so the second writer affects zero rows and loses. Its note is written in the same transaction, so a losing verdict leaves **nothing** — no note, no DM, no half-applied outcome |

A qualifier's `admins` are edited on the drill-down's **Reviewers** tab. The queue
signals its own backlog rather than waiting to be looked at: once the oldest pending
run has waited `REVIEW_BACKLOG_AGE` (6h), the expiry worker DMs the reviewer set — the
qualifier's own admins, else whoever holds `QUALIFIER_ADMIN` — at most once per
`REVIEW_BACKLOG_REMINDER` (24h), stamping `review_backlog_notified_at` before sending.
Deliberately a backlog reminder and not one DM per submission: a qualifier at real
scale takes thousands of runs. The DM lands on the queue itself
(`/admin/qualifiers?qualifier=<id>&tab=queue`), and the pending count rides on the tab
label so it is visible without opening it.

An **override** needs a reason, audits under its own action
(`async_qualifier.run_review_overridden`, with the previous status in the details),
and DMs the runner that their earlier result *changed* rather than arriving in the
shape of a first verdict. The only surface that offers it is the admin **Runs** tab's
"Change verdict" action — the review queue holds pending runs only, so a settled one
is unreachable from it.

**A runner sees a band, not a number, while the window is open.** An exact score is
exactly solvable for the seed's par — `score = (2 − elapsed/par) × 100` rearranges to
`par = elapsed / (2 − score/100)`, and the runner knows their own elapsed time — so
publishing it during the window hands out the number the lockdown exists to hide.
`list_user_runs` therefore returns an `OwnRun` projection rather than the model:
`score` is `None` until results are public and `score_band` (`under` / `near` /
`above` par) stands in. The fast side was already banded by the `SCORE_MAX` cap, so
the slow edge mirrors it at 95. `GET /{id}/me/runs` is a **separate schema** from the
reviewer's `/{id}/runs` for the same reason — fixing only the page would move the leak
one API call away. The band still bounds par, which is an accepted trade.

The same projection carries what the run surface used to withhold although the record
held it: the deadline an in-progress run auto-forfeits at, the seed played (so a runner
disputing a verdict can cite it), the reason behind a void and which of the two spent
it, and `expired_at` — so the clock's forfeit reads differently from a chosen one.

**A rejection needs a reason; an approval does not.** `review_run` refuses a rejection
with a blank note, before it writes anything — rejection is the branch that owes the
runner an explanation. The reason is stored as a run note and reaches the runner twice:
a **Reviewer note** column on their own runs table (`get_run_notes` has always let a
run's owner read its notes) and a DM carrying the reason plus a link back to the
qualifier. The reviewer's card also shows the permalink played, the runner's other runs
in this qualifier, and any notes already on the run — re-reviewing blind is how two
reviewers reach opposite conclusions about the same person.

**Two ways to spend a reattempt, both requiring a reason.** A reattempt voids one
terminal run: it stops counting toward par and score, and its pool slot frees up for a
fresh draw. It is not an undo — the voided attempt is gone, and the next run draws a new
permalink.

| Path | Who | Allowance | Where |
|---|---|---|---|
| `reattempt_run` | the runner, on their own run | spends `allowed_reattempts` | a row action on **My runs**, offered only while the window is open (voiding a run they can no longer re-run would just delete their own score) |
| `grant_reattempt` | a qualifier admin, on anyone's run | **ignores** `allowed_reattempts` | the **Runs** tab of the Manage drill-down |

The grant exists for a mis-clicked forfeit or a bad seed, so charging it to the runner's
allowance would defeat the point; `reattempt_granted_by` records which of the two
happened and is what keeps a granted void out of the runner's spent count. The Runs tab
exists because a forfeit is written straight to `APPROVED`/score 0 and so never appears
in the review queue — without it a reviewer cannot reach the very run the remedy is for.
Both paths audit (`async_qualifier.run_reattempted` / `.reattempt_granted`) and the
grant DMs the runner, because their pool availability changed without their doing
anything.

**The window is an event, not an edit.** A subscriber wants to hear "qualifying is open",
and the `PATCH` that set `opens_at` weeks earlier is no substitute for it — the state it
schedules arrives later, with no request in flight, and may never arrive at all if the
date moves again. `sync_window_state` publishes `async_qualifier.opened` /
`async_qualifier.closed` once per crossing: from the worker tick that observes the clock,
and from the service when an admin's own edit crosses it immediately (switching a
qualifier off is the one crossing the worker cannot see, since an inactive qualifier
leaves its scan). `window_state_notified` is the stamp that makes it once rather than
per tick, closing is announced only for a qualifier that was open, and there is no audit
row to pair with because nobody performed it. Run **forfeited** and **reattempted** are
events too, for the same reason `run_expired` already was: they move a standing.

**Why a run cannot be started, specifically.** `get_player_pools` returns an empty list
for five different situations, and the page used to collapse them into *"No pools
available to run right now."* — leaving the runner unable to tell whether to wait, ask an
organiser, or go home. `get_run_availability` answers instead: it never raises (a shut
window is the answer, not an error) and carries a reason plus the sentence it owes.

| Reason | What the runner is told |
|---|---|
| `NOT_ACTIVE` | This qualifier isn't accepting runs. |
| `NOT_OPEN_YET` | This qualifier opens *{when}*. |
| `CLOSED` | This qualifier closed *{when}*. The leaderboard is below. |
| `NO_POOLS` | No pools have been set up yet — check back, or ask an organiser. |
| `ALL_SLOTS_USED` | You've used all *N* of your runs in every pool. |
| `PERMALINKS_EXHAUSTED` | You've played every seed available in the pools you have runs left in. An organiser needs to add more. |
| `ANONYMOUS` | Sign in to start a run. |

The last two are the distinction the surface could never make and the reason the split
matters: only `PERMALINKS_EXHAUSTED` is something an organiser can fix. While a run *is*
still possible, each pool also shows what is left ("1 of 2 runs used").

**Scoring.** `compute_par` is the mean of the N fastest approved runs on a permalink;
`compute_score` is `clamp(0, 105, (2 − elapsed/par) · 100)` — par scores 100, twice par
scores 0, and the 105 ceiling caps what a single outlier run can be worth. Forfeits,
non-finishers and unfilled pool slots score 0. Approving or rejecting a run recomputes
that permalink's par and rescores every approved run on it, so a late submission
retroactively corrects the board rather than grandfathering an early par.

**And the surfaces say so.** Because par is a moving average, a runner's score changes
when a *stranger's* run on a seed they played is approved — correct behaviour that the
page never explained. Both the runs table and both leaderboards now carry the same
captions (`theme/qualifier_copy.py`, shared so the player and admin boards cannot
explain a column differently): scores are relative to par, 100 is par and 105 the cap;
**Score** is the realised total with unrun slots counting zero, **Estimate** projects
unrun slots at the player's own average, and ranking is by Score. The player's board
also carries the `Slots` column the admin one always had — without it "unrun slots"
names something the player cannot see.

**Active-window information lockdown.** While the qualifier is open, the leaderboard,
the pools, and the pars are staff-only (`is_results_public`). Publishing them mid-window
would tell a player who has not run yet exactly what time they need — which is the whole
advantage the async format is trying not to hand out. Everything unlocks when the
qualifier goes inactive or passes `closes_at`.
