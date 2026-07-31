# SahasrahBot lessons — status

Tracks the seven findings in
[`docs/reviews/sahasrahbot-lessons.md`](../../reviews/sahasrahbot-lessons.md)
through to code. Delete this file (and the review) once the remaining three ship.

## Shipped

| # | Finding | What landed |
|---|---|---|
| 1 | Seed provider reliability envelope | `application/utils/seed_provider.py` — one timeout/retry/classification contract every generator runs inside. Documented in [seed-generation.md](../../reference/seed-generation.md#the-provider-envelope) |
| 2 | Seed provenance | `GeneratedSeeds` records randomizer, preset, the settings **as sent**, who rolled it, and what the roll cost; qualifier permalinks FK to the same record |
| 3 | Abandoned qualifier runs | `RunExpiryMixin` + `async_qualifier_worker`: one warning DM, then an automatic forfeit that is marked `expired_at` (not a chosen forfeit) and stays appealable |
| 6a | Racetime token refresh | `RealRacetimeTransport` now re-authorizes before its token expires instead of holding a dead credential |
| 8 | Contradictory tournament config | `TournamentService._check_automation_prerequisites` refuses automatic rooms with no bot, or with nothing to roll — at save time rather than at race time |

## Still open

| # | Finding | Why it is not done here |
|---|---|---|
| 4 | Racetime readiness report | The auto-open skip is still silent. Needs a decision first: Wizzrobe's Discord surface is **DM-only** (no channel send, no per-tournament announce channel), so SahasrahBot's "post it to the event's audit channel" has to become a DM to a role plus a schedule-board surface — a UX choice, not a mechanical port |
| 5 | Stream delay | No `stream_delay` exists anywhere. Latent while the racetime room lifecycle is still scaffolding, but the design question is real: defer the *publish* (a scheduled job that can be missed) or gate the *read* on the public bracket views (simpler, cannot leak). Recommend read-gating |
| 6b | Racetime room protocol | Out of scope for a fix. When it is written, build on the official `racetime-bot` SDK — SahasrahBot spent an entire migration plan getting off its own fork |
| 7 | Crew signup fields | A product backlog item, not a defect: submitter notes, preferred commentary partner, restreamer as a distinct role, per-role signup toggles. Validated asks (the same maintainer's dormant `Schedule*` tables carry all four), but each is a new surface |

## Ground rules that applied to the shipped work

- Model → repository → service → surface, per [CLAUDE.md](../../../CLAUDE.md).
  Where a worker needs a cross-tenant scan it gets an explicitly-unscoped
  repository method with a docstring saying why, then re-enters `tenant_scope`
  per item — the shape `RacetimeRoomRepository.list_open_all` already set.
- **No new feature flags.** All five are corrections to shipped behaviour that
  every tenant already relies on; three of them ride an existing flag. A flag
  here would mean "some communities get seed rolls with no timeout".
- New `AuditActions` member ⇒ matching `EventType` member **and** an entry in
  `EventType.ALL`, because `EventType` is an external contract.
