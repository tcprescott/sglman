# Lessons from SahasrahBot

Point-in-time comparison of Wizzrobe against
[`tcprescott/sahasrahbot`](https://github.com/tcprescott/sahasrahbot) — the same
maintainer's ALTTPR race bot, in continuous production since 2019 (2,391 commits
across seven years) and still the system that actually rolls seeds for tournament
races today. Wizzrobe overlaps it on seed generation, racetime.gg
rooms, SpeedGaming ingest, async qualifiers, presets and Discord notification —
so its scar tissue is directly transferable.

Read the way the other `docs/reviews/` files are read: transient, delete once the
findings ship.

## Method

Full clone with history. Reviewed: `CLAUDE.md`, `docs/design/*` and `docs/plans/*`
(especially the seed-provider reliability contract, the non-async tournament
reliability audit, and the self-service tournament design), the three-tier
package layout, the racetime bot core, the async-tournament services, and the
commit log filtered for operational fixes (`timeout`, `retry`, `crash`,
`duplicate`, `rate limit`, `reconnect`, `stale`). Each finding below was then
checked against the current Wizzrobe tree.

## What SahasrahBot has already converged on that Wizzrobe matches

Worth stating first, because it means the architecture is not the thing to change:

- **The same three-layer split, with the same enforcement instinct.** SahasrahBot
  finished a multi-phase migration in 2026 into
  `presentation/ → services/ → repositories/ → models/`, enforced by
  `import-linter` contracts blocking in CI. Wizzrobe's `enforce_architecture.py`
  hook is the same rule reached from the other direction.
- **A single serial notification queue.** `alttprbot/services/_notify/queue.py` is
  Wizzrobe's `application/services/discord/discord_queue.py` — one worker, failures
  logged not swallowed, enqueue-before-start safe. Wizzrobe's is strictly ahead:
  it re-binds the enqueuer's tenant onto the coroutine, which SahasrahBot has no
  need for.
- **Config-not-code tournaments.** SahasrahBot's biggest documented regret
  (`docs/design/self_service_tournaments.md`) is that 23 tournaments each need a
  Python subclass and a deploy, and *half of them exist only to carry
  configuration values*. Its approved fix — a DB record plus a named-roller
  registry — is what Wizzrobe already shipped as `tournament_strategies/` plus
  the `Tournament` config columns. Do not drift back toward per-tournament code.
- **Background loops that survive a tick.** Both wrap per-item work so one bad
  item never stops the others. Wizzrobe's `for_each_tenant_scoped` +
  `run_worker_loop` is the cleaner version of SahasrahBot's `try/except` inside
  each `tasks.loop`.
- **Durable interaction handling.** Wizzrobe's `custom_id`-prefix dispatch in
  `discordbot/` avoids the persistent-view re-registration dance SahasrahBot has
  to do on every `on_ready`.

So the lessons below are all operational, not structural.

---

## 1. Seed generation has no reliability envelope — the highest-value gap

SahasrahBot wrote a formal contract for this after years of provider outages
(`docs/design/seed_provider_reliability_contract.md`, implemented in
`alttprbot/services/seedgen/provider_wrapper.py`): **every** outbound provider
call goes through one wrapper enforcing a 60s per-attempt timeout, 3 attempts
with exponential backoff, a retryable/non-retryable classification (429 and 5xx
retry; 4xx and local validation errors do not), and a normalized exception
taxonomy — `SeedProviderTimeoutError`, `SeedProviderUnavailableError`,
`SeedProviderRateLimitError`, `SeedProviderInvalidRequestError`,
`SeedProviderResponseFormatError` — each carrying `provider`, `operation`,
`attempts`, `status_code` and the provider's own message. Surfaces are forbidden
from carrying their own retry or audit logic.

Wizzrobe's `application/services/seedgen_service.py` is the pre-contract shape:
each randomizer opens its own client with no timeout and no retry —
`aiohttp.ClientSession()` at `:263` (Map Rando), `aiohttp.request(...)` at `:285`
(OOTR), `ClientSession(headers=...)` at `:344` (DK64R, which additionally *polls*
a task queue). A hung upstream ties up the request until the platform default
gives out; a 502 during a tournament is a hard failure where a single retry would
have succeeded.

This is the gap most likely to be felt live, and the fix is well-specified by
someone who has already paid for it. Route every provider call through one
`execute_with_contract`-style wrapper in `application/utils/clients/` (or a
`seedgen/` submodule), and let `ValueError` surface the provider's message the
way the contract prescribes.

## 2. Rolled seeds have no provenance

The contract's audit-parity clause requires that *every* successful generation
write one record with `randomizer`, `gentype`, `genoption`, `permalink`,
`hash_id`, the **raw effective settings payload**, and provider metadata
(`provider`, `operation`, `attempt_count`, `latency_ms`, `surface`). SahasrahBot
additionally keeps `TournamentPresetHistory` (preset, who rolled it, which
episode, which event, when).

Wizzrobe's `GeneratedSeeds` (`models/tournament.py:157`) stores `seed_url`,
a free-text `seed_info`, and timestamps. There is no record of which `Preset` and
which settings blob actually produced it, who triggered it, or for which match.
Presets are editable rows (`Preset.settings`, `models/tournament.py:166`), so
editing a preset silently rewrites the apparent history of every seed rolled from
it. When a result is disputed — the case this data exists for — the question
"what settings did this seed actually use?" is currently unanswerable.

Snapshot the resolved settings onto the generated-seed row, plus
randomizer/preset/actor/match and the provider metadata above.

## 3. An abandoned qualifier run never ends

March 2023, commit `9865939` — "add async in progress timeout of 12 hours". A
`tasks.loop` sweeps `status='in_progress'` async races and force-forfeits ones
past their deadline, alongside a separate `timeout_warning_task` that warns the
runner *before* the deadline lands. Both exist because in an async qualifier
people open a run and disappear, and a permanently in-progress run holds a
permalink assignment, distorts the leaderboard, and blocks the runner's own
retry.

Wizzrobe creates runs as `AsyncQualifierRunStatus.IN_PROGRESS`
(`application/services/async_qualifier/async_qualifier_service.py:462`) with a
server-stamped `started_at` (`models/async_qualifier.py:144`), and nothing ever
reaps them — none of the five registered workers (`main.py:137-160`) touches
qualifier runs, and `async_qualifier_rules.py` contains no expiry rule.

Add a reaper tick and a pre-deadline warning DM. The per-qualifier allowance is
already modelled; this is the enforcement half.

## 4. Racetime eligibility fails silently at the moment it matters

SahasrahBot runs `find_races_with_bad_discord` every four hours, posting to each
event's audit channel the upcoming races whose players have stale or unresolvable
Discord identities — because SpeedGaming identity data is user-entered and rots,
and the failure otherwise surfaces during the live race-setup window. The
non-async reliability audit lists this as finding 4, with the report loop as the
*existing mitigation*.

Wizzrobe's auto-open gate is the same class of dependency: a room only opens when
every entrant has a linked racetime identity
(`application/services/race_room_service.py:137-144`). When one hasn't linked, the
worker logs `auto-open skipped ... not all entrants have linked racetime` and
returns `None`. Nobody is told. The first person to notice is a player standing in
front of a room that was never created, minutes before their match.

Turn the silent skip into a readiness report: a scheduled scan of upcoming matches
whose entrants are unlinked, surfaced on the schedule board and to the tournament's
Discord channel with enough lead time to fix it.

## 5. There is no stream delay anywhere in Wizzrobe

`stream_delay` is a first-class field throughout SahasrahBot — on the tournament
definition (`alttprbot/services/tournament/definition.py:54`, e.g. `stream_delay=10`
for ALTTPR DE and League), folded into the room-open computation
(`services/tournament/core.py:333`), and used by the results-recording task to
hold a write back so a spoiler or finish time is not published while the restream
is still behind live.

`grep -rn stream_delay` over Wizzrobe returns nothing. Today that is latent — the
racetime room lifecycle is scaffolding (see 6) — but the moment rooms capture
finish times and seeds carry spoiler logs, publishing on the real clock leaks the
race to the restream audience. The concept belongs on `Tournament` next to
`room_open_minutes_before`, and every publish path (results, spoiler attach,
webhooks, Discord embeds) has to respect it.

## 6. Don't hand-roll the racetime protocol

Wizzrobe's `racetimebot/` is honest about its scope: `transport.py` proves OAuth
client-credentials and tracks liveness, `handler.py`'s `RoomStatusLifecycle` mirrors
status, and the docstrings say the real websocket protocol is "the integration
surface later PRs build on." The connection loop is genuinely good — capped
exponential backoff, auth errors that stop retrying instead of hammering a bad
secret, interruptible sleep, tenant-routed dispatch.

Two things SahasrahBot learned about what comes next:

- **Use the official SDK.** SahasrahBot ran a maintained *fork* of `racetime-bot`
  for years and spent a whole migration plan
  (`docs/plans/racetime_bot_official_migration_plan.md`) getting back onto upstream
  2.3.0 — reconciling a changed websocket model, a changed handler constructor, and
  re-porting helpers upstream had dropped. Wizzrobe has not yet written the
  protocol layer, so it can start on `racetime_bot.Bot` / `RaceHandler` and never
  own that fork.
- **Token refresh must recycle connections.** `alttprbot/presentation/racetime/core.py`
  re-authorizes on a loop, subtracting a 10-minute safety margin from the token
  lifetime, and then *closes every open room websocket* (with a 30s close timeout)
  so each reconnects with the fresh token. Long-lived race rooms outlive a token;
  without this the connections die mid-race. Wizzrobe's loop currently fetches a
  token per connection attempt and has no in-flight refresh path.

Also worth copying when the handler layer lands: SahasrahBot's per-room seed
commands are **gatekept** — only racetime volunteer/monitor team members or
configured helper roles may roll (`can_gatekeep`), and duplicate-room prevention
plus cancelled-room cleanup run before any creation. Wizzrobe has the second via
`get_by_match`; the first has no equivalent yet.

## 7. Crew signup: the fields SahasrahBot's second attempt added

`alttprbot/models/schedule.py` is a dormant, never-wired scheduling system —
tables created by migrations 84-94, no service or UI ever built. It is, in effect,
the first draft of Wizzrobe. Its shape agrees with Wizzrobe's (`approved`,
`approved_at`, `approved_by` per crew role — compare `models/match.py:155-190`),
which is reassuring, but it carries four things Wizzrobe does not:

| Field | Why it exists |
|---|---|
| `submitter_notes` on each signup | "I can only do the first hour", "I've commentated this matchup before" — the context a coordinator needs to approve, currently unsendable |
| `ScheduleEpisodeCommentatorPreferredPartner` | Commentary is a duo act; people volunteer *with* someone. Without it, coordinators pair by hand off Discord |
| `runner_notes` / `private_notes` on the episode | Player-visible vs staff-only annotation, separated |
| Per-event `open_*_signup` toggles + `max_*` counts | Wizzrobe has `required_commentators` / `required_trackers` (a coverage target) but no ceiling and no per-role signup switch |
| `ScheduleEpisodeRestreamer` + `ScheduleBroadcastChannels` | Restreamer is a distinct crew role from commentator/tracker; Wizzrobe models neither it nor the Twitch channel a match is broadcast on |

Treat this as a backlog of validated asks, not a design to copy — the tables were
never used, but the fields were chosen by the same person from the same community's
complaints.

## 8. Fail fast at startup, on config *and* on handlers

SahasrahBot has `helpers/validate_runtime_config.py` plus `alttprbot/util/config_contract.py`
as a documented pre-run step, and builds its racetime bots at startup rather than
import specifically so credential validation happens loudly at boot
(`fix(racetime): build bots at startup, not import`). Its reliability audit then
asks for the same treatment one level up: *"add startup validation that every
enabled handler can build config and resolve required channels/roles"* and
*"explicit protocol checks for required methods per handler type at registration
time"* — both written because a missing override or an unresolvable channel ID
currently fails during a live race-setup window instead of at deploy.

Wizzrobe's equivalent exposure is per-tenant config: a tournament with
`racetime_auto_create_rooms` on but no authorized bot, or `discord_events_enabled`
with a channel the bot cannot see, is only discovered by the worker that skips it.
A validation pass — at save time in the admin UI, and as a periodic health check
next to `service_health_worker` — converts those into a visible warning.

---

## Suggested order

| # | Lesson | Why here |
|---|---|---|
| 1 | Seed provider reliability envelope (§1) | Live failure mode today; the contract is already written |
| 2 | Seed provenance (§2) | Small schema change, unblocks dispute resolution, cheapest to do alongside §1 |
| 3 | Qualifier run reaper + warning (§3) | Self-inflicted data corruption, one worker |
| 4 | Racetime readiness report (§4) | Turns a silent skip into a fixable warning |
| 5 | `stream_delay` (§5) | Cheap now, a spoiler leak later |
| 6 | Racetime protocol on the official SDK, with token-refresh recycling (§6) | Design-time decision — settle it before the handler layer is written |
| 7 | Crew signup fields (§7) | Product backlog, no urgency |
| 8 | Startup/save-time config validation (§8) | Broad, best done incrementally |
