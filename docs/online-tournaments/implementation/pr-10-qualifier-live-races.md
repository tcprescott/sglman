# PR 10 — Async Qualifier live races

> Feature 1 + 5. Roadmap phase 8. Synchronous group runs on racetime, reusing the
> Feature 5 racetime subsystem.
>
> **Status: implemented (PR 10).** `AsyncQualifierLiveRace` (FKs → pool + nullable
> permalink/episode; `match_title`; globally-unique nullable `racetime_slug`;
> `AsyncQualifierLiveRaceStatus`) + the deferred `AsyncQualifierRun.live_race` FK
> (migration 29; leak test). `AsyncQualifierLiveRaceService` authors a race, opens
> a `RacetimeRoom` (`match=None`) via a tenant-authorized bot and mirrors its slug,
> and captures each racetime entrant into an `AsyncQualifierRun` on finish
> (done→finished, dnf→forfeit, dq→disqualified; `finish_time`→elapsed), then
> par-scores. `RaceRoomLifecycle` routes a match-less room to this path by slug,
> reusing the PR 4/6 subsystem. Admin **Live Races** sub-tab (create + open room).
> `async_qualifier.live_race_*` audit; `live_race_recorded` event. **Decisions
> taken here:** live-race runs **skip reviewer sign-off** (written `APPROVED` — the
> racetime result is self-attributing) and are par-scored like any other approved
> run; **recording is refused while any entrant is still racing**; the room's
> category/bot is the tenant's first authorized bot (no per-qualifier bot FK). See
> [current-state.md](../../current-state.md),
> [data-model.md](../../reference/data-model.md), and
> [services.md](../../reference/services.md).

**Goal:** a qualifier pool flagged `live_race` can run as a synchronous racetime
race whose results flow into `AsyncQualifierRun`s.

**Depends on:** PR 4 (bot runtime), PR 6 (room lifecycle), PR 9 (qualifiers).
**Unblocks:** nothing.

## Deliverables

- **`AsyncQualifierLiveRace`** model (port sahabot2): FKs → pool and nullable →
  permalink, `match_title`, `racetime_slug` (unique), optional `episode_id` FK to an
  SG-imported episode, `status` enum (`scheduled/pending/in_progress/finished`).
  Migration + leak test.
- **Reuse the PR 4/6 racetime subsystem** to open and drive the live-race room —
  **not** a separate integration. On finish, capture each entrant from the room
  (racetime status → run status: `done`→finished, `dnf`→forfeit, `dq`→disqualified;
  `end_time` from finished_at) into the corresponding `AsyncQualifierRun`s.
- **Review/scoring path** ([gap live-race-result-capture](../gap-analysis.md)):
  decide and implement whether a live-race run **skips review** (self-attributing
  racetime result) or still requires reviewer sign-off; then par-score it like any
  other run. Recording requires the live race in-progress and aborts if any entrant
  is still racing ("record again later").
- `async_qualifier.*` / `race_room.*` events as appropriate.

## Decisions that apply

Live races reuse the racetime subsystem; run statuses shared with the async model.

## Reference implementations

- **sahabot2**: `application/services/async_qualifiers/async_live_race_service.py`,
  `models/async_tournament.py` (`AsyncTournamentLiveRace`),
  `components/dialogs/async_qualifiers/create_live_race_dialog.py`.
- **sglman (this plan)**: PR 4 `racetimebot/`, PR 6 `RaceRoomService` (the same
  finish-capture machinery, targeting runs instead of `MatchPlayers`).

## Acceptance criteria

- A live-race pool opens a racetime room (mocked), N entrants finish, and each
  entrant's `AsyncQualifierRun` gets the captured time/status and a par score; the
  leaderboard reflects it. Recording is refused while an entrant is still racing.

## Out of scope

Any change to scheduled-match room lifecycle (PR 6 owns it).
