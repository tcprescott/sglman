# Plan 1 — tell the runners they are on stage

**Read [README.md](README.md) first.**

Assigning a stage currently changes a database row and refreshes an open page.
The two people it most concerns learn about it when somebody walks over and
tells them. This plan sends a DM when the stage is set or cleared, and a second
one shortly before the match.

| Task | Size |
|---|---|
| T1.1 | Two columns + migration | small |
| T1.2 | The three DM builders | small |
| T1.3 | Fan-out from `assign_stage` | medium |
| T1.4 | The reminder worker | medium |
| T1.5 | Tournament dialog control | small |
| T1.6 | Seed + docs | small |

No feature flag. No new `AuditActions`, no new `EventType`.

---

## T1.1 — Store the lead time and the stamp

`models/tournament.py`, beside the racetime block:

```python
    # How long before a scheduled match to remind its players and approved crew
    # which stage they are on. Deliberately separate from
    # ``room_open_minutes_before`` above, which governs racetime room creation:
    # the two answer different questions and a community will want different
    # numbers for them.
    stage_reminder_minutes = fields.IntField(default=30)
```

`models/match.py`:

```python
    # Set when the stage reminder for this match has been sent, so the worker
    # fires once. Cleared whenever the stage changes, which re-arms it.
    stage_reminder_sent_at = fields.DatetimeField(null=True)
```

```bash
poetry run aerich migrate --name add_stage_reminder_fields
poetry run aerich upgrade
```

**Read the generated migration before continuing.** It must add exactly two
columns. `aerich migrate` recomputes its numeric prefix from the `aerich`
table's insertion order rather than from filenames, and has been observed
unlinking an existing version file that collides with it. Run
`git status migrations/` afterwards and confirm the only change is your new
file.

Neither model is new, so `test_leak_test_coverage.py` needs nothing and
`test_seed_coverage.py` needs no new row. Both models are already tenant-scoped.

---

## T1.2 — The DM copy

`application/utils/discord_messages.py`, three builders beside the existing
match ones. Times go through `discord_embeds.time_field` so each recipient's
client renders them in their own zone; never format a time into these strings.

- `stage_assigned_dm(tournament, stage_name, when, player_names)` — "Your match
  is on **Kraid**." Says plainly that the match happens on the stage rather than
  in the tournament room, because that substitution is the actual information.
- `stage_cleared_dm(...)` — the retraction. Says the match is back in the
  tournament room.
- `stage_reminder_dm(...)` — the nudge, naming the stage and the time.

Plus `stage_embed(...)` in `application/utils/discord_embeds.py`, following
`match_embed`. Pick a colour constant that is not already in use for scheduled
or rescheduled.

Every one of the three carries a `DMLink`. There is no stage-specific link
target yet; add one to `application/services/notification_links.py` beside the
existing player-facing targets:

```python
async def player_match(match_id: int, *, label: str = 'View your match') -> Optional[DMLink]:
```

pointing at the Player tab with the match open. `admin_match` already exists but
lands on the admin board, which a player cannot open — the third failure named
in CLAUDE.md's calls-to-action rule, and the one that looks correct until
somebody taps it.

**Copy review before you write the code.** Run these through the writing rules:
no "underscore", "ensure", "please note"; contractions; one em dash maximum.

---

## T1.3 — Fan out from `assign_stage`

`application/services/match/match_service.py:560`. The method already audits,
publishes and calls `match_live.publish`. Add, after the repository update and
before the audit:

```python
        await self.repository.update(match, stage_id=stage_id, stage_reminder_sent_at=None)
```

Clearing the stamp on every change is what re-arms the reminder when a stage is
reassigned, and it is why the stamp lives on the match rather than being derived.

Then enqueue the fan-out. The recipients are the match's players and its
**approved** crew — a pending commentator has not been given the job and should
not be told to be somewhere. `_schedule_notifications.py` already computes that
audience for `notify_match_crew`; reuse it rather than writing a second version.

Sends go through `discord_queue.enqueue`, never awaited inline: `assign_stage`
runs from a table-cell handler on the schedule board, and a slow Discord call
there blocks the shared event loop.

Both branches send: `stage_id is not None` gets `stage_assigned_dm`, the clear
branch gets `stage_cleared_dm`. The existing audit and event calls are untouched
— `MATCH_STAGE_ASSIGNED` and `MATCH_STAGE_CLEARED` already exist in both
`AuditActions` and `EventType`.

**No new event for the DM itself.** The notification is a consequence of the
stage change, not a separate fact, and the audit pair already records it.

---

## T1.4 — The reminder worker

New `application/services/match/stage_reminder.py`, modelled closely on
`application/services/volunteer/volunteer_reminder.py` — read that file first,
it solves this exact problem for a different row.

The shape it establishes and this must copy:

- `TICK_SECONDS = 60`, `run_worker_loop(_tick, TICK_SECONDS, name=...)`.
- A **cross-tenant** scan over a generous fixed window, because the loop cannot
  know each tournament's lead before it has the rows. Then a per-match re-check
  against that match's own tournament lead, leaving anything outside the window
  unstamped so a later tick catches it.
- `MAX_LEAD_MINUTES` as a bound on the scan, with a warning log when a
  tournament's configured lead exceeds it. A day is generous here; a stage call
  further out than that is not a reminder.
- **Stamp before sending**, so a delivery failure or a restart never re-fires.
- `for_each_tenant_scoped(...)` so each DM is built inside its own
  `tenant_scope` and its `DMLink` resolves to the right community URL.

`MatchRepository` gains the query, with a docstring saying it is deliberately
unscoped:

```python
    @classmethod
    async def due_for_stage_reminder(cls, now, window_end):
        """Matches whose stage reminder may be due, across every tenant.

        Deliberately unscoped: the worker scans all tenants in one pass and
        re-checks each match against its own tournament's lead. Callers outside
        the worker want the scoped reads.
        """
```

Filter on: `stage_id__isnull=False`, `scheduled_at__gte=now`,
`scheduled_at__lte=window_end`, `stage_reminder_sent_at__isnull=True`,
`finished_at__isnull=True`, `cancelled_at__isnull=True` (confirm the real
cancellation column before writing this). Prefetch `tournament`,
`players__user`, `stage` and the approved crew relations so the send does no
per-row queries.

Register in `main.py` beside `volunteer_reminder.start()`, and add the matching
`await stage_reminder.stop()` in the shutdown block. Both halves — a worker
started and never stopped holds the process open on shutdown.

No feature-flag skip: this plan adds no flag, and the matches it reads exist for
every tenant.

---

## T1.5 — The tournament dialog control

`theme/dialog/tournament_edit_dialog.py`, a number input beside the racetime
block where `room_open_minutes_before` already lives (around line 367). Label
and help text must distinguish the two clearly; they sit next to each other and
both are "minutes before", which is exactly how someone sets the wrong one.

Wire it through `TournamentService.create_tournament` and `update_tournament`
alongside `room_open_minutes_before` (lines 201, 301, 371) and into
`TournamentRepository.create`.

---

## T1.6 — Seed and docs

`scripts/seed_dev.py`: one tournament with a non-default
`stage_reminder_minutes` so the per-tournament path is exercised rather than the
default, and one scheduled match with a stage assigned and
`stage_reminder_sent_at` still null, so the worker has something to find on a
fresh seed. Idempotent `get_or_create`, tenant-threaded like its neighbours.

Docs: `docs/reference/data-model.md` (both columns),
`docs/features/discord.md` (the three DMs, their audience, their link target),
`docs/features/match-participation.md`, `docs/reference/services.md` (the
worker).

---

## Tests

`tests/services/test_match_stage_notifications.py`:

- assigning a stage DMs both players and every approved crew member
- a pending, unapproved crew signup receives nothing
- clearing the stage sends the retraction and nulls `stage_reminder_sent_at`
- assigning, clearing and re-assigning arms the reminder twice, which is the
  regression the stamp-clearing exists to prevent
- every DM carries a `DMLink` whose URL is absolute and tenant-qualified

`tests/test_stage_reminder_worker.py`:

- fires exactly once inside the window
- a second tick after a send does nothing
- a match with no stage is never picked up
- a finished match is never picked up
- a tournament with a 90-minute lead is reminded at 90, not 30
- a lead beyond `MAX_LEAD_MINUTES` logs a warning and the match is still
  reminded once it enters the scan window

Use `tests/factories.py` and the hoisted conftest fixtures. The DRY hook flags a
local `make_user`, `utc` or `app` copy. No test may touch the network; the
conftest socket guard will fail it.

No tenancy test and no API matrix: no new model, no new endpoint.
