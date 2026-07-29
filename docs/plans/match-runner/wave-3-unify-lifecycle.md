# Wave 3 — one lifecycle path

**Read [README.md](README.md) first. Waves 1 and 2 must be merged.**

The first wave where behaviour changes. Waves 1–2 were about *who may press the
buttons*; this is about the fact that **racetime never presses them at all**.

| Task | Fixes | Size |
|---|---|---|
| T3.1 | racetime bypasses audit, events and notifications | medium |
| T3.2 | `_settle_bracket` exists only because racetime never confirms | small |
| T3.3 | retire `is_racetime_enabled` | small |

**This wave changes what event subscribers see.** Read T3.1's "Blast radius"
before starting, and say so plainly in the commit message.

---

## The problem, precisely

`application/services/race_room_service.py` writes match state directly:

```python
    async def mark_in_progress(self, room, *, actor=None):
        ...
        if match is not None and match.started_at is None:
            if match.seated_at is None:
                match.seated_at = now
            match.started_at = now
            await match.save()
```

and in `record_finish`:

```python
        for mp, (rank, ftime) in results.items():
            mp.finish_rank = rank
            mp.finish_time = ftime
            await mp.save()
        ...
            match.finished_at = now
            await match.save()
```

`MatchScheduleService._transition` — the path every human action takes — does
*authorize, validate, stamp, audit, notify* and publishes the matching
`EventType`. The racetime path does none of that for the match. It publishes
`RACE_ROOM_STARTED` / `RACE_ROOM_FINISHED` about the **room**, and one
`MATCH_RESULT_RECORDED` with `'source': 'racetime'`.

Consequences:

- A webhook subscribed to `MATCH_STARTED` never fires for an online match.
  Same for `MATCH_FINISHED`.
- No player notification is sent. (Arguably fine — the players are in the race
  room. Decide deliberately; see T3.1.)
- No audit row in the `match.*` namespace, so the audit viewer's match history
  is incomplete for online matches.
- `_settle_bracket` had to be invented to work around the missing confirm.

---

## T3.1 — Route racetime through the lifecycle service

### The shape

Do **not** make `race_room_service` call `seat_match` / `start_match` /
`finish_match`. Those authorize a human actor and run `check()` preconditions
written for a human (`"Match is already checked in"`), and the racetime path
arrives with a system actor and out-of-order events.

Instead, give `MatchScheduleService` a **system-transition** entry point that
shares `_transition`'s tail (stamp, audit, publish, optional notify) while
skipping the human gate:

```python
    async def apply_external_transition(
        self,
        match: Match,
        actor: User,
        *,
        to_state: str,                 # 'seated' | 'started' | 'finished'
        at: datetime,
        notify: bool = False,
    ) -> None:
        """Stamp a lifecycle transition driven by the match's own runner.

        The runner already decided this happened — there is no human to
        authorize and no precondition to enforce, so this skips the gate and
        the ``check()`` that ``_transition`` applies to a person pressing a
        button. It exists so an externally-run match still produces the same
        audit rows and events as a proctored one; without it a subscriber
        watching MATCH_STARTED never hears about an online match.

        Idempotent: a transition already stamped is a no-op, because racetime
        can replay a room's state.
        """
```

Guard it: assert `match.tournament.runner.drives_lifecycle` and raise otherwise,
so this can never become a back door around the human gate. That assertion is
the reason the runner type is worth having here.

Then `mark_in_progress` and `record_finish` call it instead of assigning
timestamps. Keep the `RACE_ROOM_*` audit/events exactly as they are — they
describe the room and remain useful; this adds the `match.*` half that was
missing.

### Decide, and write down, whether to notify

`notify=False` is the safe default and preserves today's behaviour. A player in
a racetime room does not need a "your match started" DM — they are looking at
it. But a *watcher* might. Pick one, state the reasoning in the docstring, and
do not leave it accidental. If in doubt ship `notify=False`; it is the
non-change.

### Idempotency matters here

racetime can re-deliver room state. Today's code guards with
`if match.started_at is None`. Preserve that inside
`apply_external_transition` — a second call must not write a second audit row
or republish the event. Test it explicitly.

### Blast radius

New events now fire that did not before: `MATCH_STARTED` and `MATCH_FINISHED`
for every racetime match. That reaches:

- **outbound webhooks** (`docs/features/webhooks.md`) — a tenant subscribed to
  those event types starts receiving deliveries they never got. This is the
  intended fix, but it is a visible change to an external contract.
- **telemetry's event mirror** (`docs/features/telemetry.md`)
- **`match_live`** UI nudges, if `_transition` publishes one

Check each before shipping and say in the commit message that online matches now
emit match lifecycle events.

### Tests

`tests/services/test_race_room_service.py` (find the real file first):

```python
async def test_marking_in_progress_emits_match_started(db)
async def test_recording_a_finish_emits_match_finished(db)
async def test_replayed_room_state_does_not_double_stamp(db)
async def test_replayed_room_state_does_not_double_audit(db)
async def test_external_transition_is_refused_for_an_onsite_runner(db)
```

The last one pins the guard: an on-site match must not be transitionable
without a human.

---

## T3.2 — Reconsider `_settle_bracket`

**Depends on:** T3.1.

`race_room_service._settle_bracket` exists because "a racetime finish stamps
`finished_at` but never *confirms* the match, and `advance_if_linked` hangs off
`confirm_match`, whose only callers are human" — its own docstring.

**Do not delete it, and do not make racetime auto-confirm.** Confirmation is the
admin's verification step (README design decisions), and that holds for online
matches too — an online result can be disputed just as an on-site one can.

What to do instead: leave the behaviour alone and fix the *explanation*. Now
that a runner type exists, the docstring should say that a runner which
`reports_result` still does not confirm, and that settling the bracket game is
the deliberate compensation. Add a test pinning that a racetime finish leaves
`confirmed_at` null, so nobody "fixes" it later.

If you conclude the compensation is wrong and online matches *should*
auto-confirm, **stop and ask** — that is a product decision, not a refactor.

---

## T3.3 — Retire `is_racetime_enabled`

**Depends on:** T3.1, T3.2.

Wave 1 kept `Tournament.is_racetime_enabled` because the racetime services, the
SpeedGaming ETL and the online-tournament pages read it. Now enumerate them:

```bash
grep -rn "is_racetime_enabled" --include=*.py .
```

For each caller decide honestly:

- **Asking a capability** ("can I check in?") → convert to `runner.<capability>`.
- **Genuinely asking about the racetime integration** ("do I have a bot to open
  a room with?") → that is not a capability question. Leave it, but change it to
  read `racetime_bot_id` directly, which is what it means.

Then delete the property. If any caller resists both readings, leave the
property, say which caller and why, and do not force it.

`RUNNER_FILTERS` in the repository keeps `racetime_bot_id__isnull` — that is the
one place the derivation is allowed to live until wave 4 replaces it.

---

## Wave 3 wrap-up

```bash
poetry run pytest
scripts/ui_flag_sweep.sh
```

Then exercise a racetime match end to end in dev. The seed's racetime tournament
has race-room fixtures; drive one to in-progress and finished and check:

- `match.started_at` / `finished_at` are stamped exactly once
- the audit log shows `match.started` / `match.finished` **and** the
  `race_room.*` rows
- `confirmed_at` stays null
- a bracket-linked racetime game still settles

The audit viewer (Admin → Reports) is the quickest way to read that trail back.

Commit as *"Give externally-run matches the same audit and events as proctored
ones"*, and state that online matches now emit `MATCH_STARTED` / `MATCH_FINISHED`.
