# Wave 4 — the admin's verify-and-confirm loop

**Read [README.md](README.md) first.** **Waves 1–3 must be merged** — T4.1 assumes
the proctor and admin boards are separate views (T3.1), and T4.2 builds on the
result dialog from T3.3.

The proctor's half is now coherent. The admin's half is not: their review queue is
excluded by the default filter, they cannot correct a result they disagree with,
confirming validates nothing, and there is no way for a proctor to say "this one
is contested".

| Task | Fixes | Depends on | Size |
|---|---|---|---|
| T4.1 | F14 | T3.1 | medium — includes a shared-state bug fix |
| T4.2 | F15 | T3.3 | medium |
| T4.3 | F16 | — | small |
| T4.4 | F17 | T4.1, T4.2 | **large** — migration + REST + events |
| T4.5 | F18 | — | small |

T4.4 is the only genuinely new capability in the whole plan and it only makes
sense once T4.1–T4.3 exist. Do it last.

---

## T4.1 — Surface the review queue (and stop the four boards sharing one filter)

**Why.** `DEFAULT_STATE_FILTER` is `['Scheduled', 'Checked In', 'Started']` —
`Finished` is not in it. The admin's entire job is the
Finished-not-yet-Confirmed set, and to see it they must notice the State filter
and add a chip. There is no queue, no count, no badge.

**The blocker you must fix first.** All four `MatchTableView` instances (home
schedule, player dashboard, admin schedule, proctor board) persist their filters
under the *same* tenant-session keys — `state_filter`, `tournament_filter`,
`stream_room_filter` (`theme/tables/match.py` lines ~99, ~105, ~111, ~226).
Changing the state filter on one board silently changes it on the other three,
and any per-board default is overwritten by whichever board the user visited
last. Give each view its own namespace or T4.1 cannot work.

### Files

- `theme/tables/match.py`
- `pages/admin_tabs/admin_schedule.py`
- `pages/volunteer_tabs/proctor_station.py`
- `pages/home_tabs/schedule.py`, `pages/home_tabs/player.py`

### Change 1 — namespace the stored filters per view

`theme/tables/match.py`. Add a required-in-practice `storage_key: str = 'match'`
to `MatchTableView.__init__` and route every `tenant_session_get` /
`tenant_session_set` through a helper:

```python
    def _skey(self, name: str) -> str:
        """Session key for one of this view's filters.

        Namespaced per view: four boards share one session, and before this a
        filter change on the admin Schedule tab silently retargeted the home
        schedule board and the proctor station too.
        """
        return f'{self.storage_key}:{name}'
```

Replace all six call sites (`'state_filter'`, `'tournament_filter'`,
`'stream_room_filter'` in both the change handlers and the loaders) with
`self._skey('state_filter')` etc.

Then pass a distinct `storage_key` from each construction site:
`'admin_schedule'`, `'proctor'`, `'home_schedule'`, `'player_dashboard'`.

This resets everyone's stored filters once, which is correct — the old shared
value was meaningless.

### Change 2 — a per-view default state filter

Add `default_state_filter: Optional[list] = None` to `__init__`, and in
`_setup_ui` (~line 226):

```python
                    default_states = tenant_session_get(
                        self._skey('state_filter'),
                        list(self.default_state_filter or DEFAULT_STATE_FILTER),
                    )
```

`_active_filter_count` (~line 145) compares against `DEFAULT_STATE_FILTER` to
decide whether the mobile badge shows; change it to compare against
`self.default_state_filter or DEFAULT_STATE_FILTER` so the badge does not claim
the default is a custom filter.

`pages/admin_tabs/admin_schedule.py` passes:

```python
            storage_key='admin_schedule',
            default_state_filter=['Scheduled', 'Checked In', 'Started', 'Finished'],
```

Leave the proctor board and the two home boards on the shared default.

### Change 3 — a needs-review chip on the admin board

In `admin_schedule_page`, above the table, add a `@ui.refreshable` strip driven by
the `on_rows_changed` hook added in T3.2:

```python
        @ui.refreshable
        def review_queue() -> None:
            rows = table_view.table.rows if table_view else []
            pending = [r for r in rows if r.get('state') == 'Finished']
            if not pending:
                return
            with ui.row().classes('items-center gap-2 q-mb-sm'):
                ui.html(
                    f'<span class="wiz-chip wiz-chip--pending">'
                    f'<span class="q-mr-xs">flag</span>Awaiting confirmation: {len(pending)}</span>'
                )
                ui.button('Show only these', icon='filter_alt',
                          on_click=lambda: _only_finished()).props('flat dense color=primary')

        def _only_finished() -> None:
            table_view.state_filter.value = ['Finished']   # fires the change handler
```

Because the default now includes `Finished`, the queue is visible without any
click; the chip and the button are the affordance for focusing on it.

### Tests

`tests/theme/test_match_table_storage_keys.py` — the regression that matters:

```python
def test_two_views_do_not_share_a_filter_key():
    a = MatchTableView.__new__(MatchTableView); a.storage_key = 'admin_schedule'
    b = MatchTableView.__new__(MatchTableView); b.storage_key = 'proctor'
    assert a._skey('state_filter') != b._skey('state_filter')
```

(Constructing the view for real needs a NiceGUI slot context; `__new__` plus the
attribute is enough to lock the key derivation.)

Add a test that `default_state_filter` is honoured when nothing is stored, and
that a stored value still wins.

### Verify

As `staff_user`, load `/admin/schedule` in a fresh browser context: the State
filter must show four chips including `Finished`, at least one Finished row must
be visible, and the "Awaiting confirmation: N" chip must match the count. Then
switch to `/volunteer/proctor-station` as `proctor_user` and confirm its filter is
still the three-state default — changing one must not move the other.

---

## T4.2 — Let an admin correct a recorded result

**Depends on:** T3.3.

**Why.** `AdminMatchDialog` (`theme/dialog/match_dialog.py`) edits tournament,
stage, players, commentators, trackers and racetime — there is **no winner or
result field**. Once a match is `Finished` the Finish button is gone, so the
result dialog is unreachable. For a bracket-linked match
`assert_bracket_result_editable` at least points staff at *Results → Override*;
for everything else the only correction path is the REST endpoint. This blocks
the agreed model — *proctor records best guess, admin overrides at confirmation*.

**No service change is needed.** `MatchService.record_match_result` already
re-records for a non-bracket match, and raises a clear `ValueError` for a settled
bracket game. This task is entirely about reaching it from the UI.

### Files

- `theme/tables/match_slots.py`, `theme/tables/match_grid.py`
- `theme/tables/match.py`, `theme/tables/match_handlers.py`
- `theme/tables/match_lifecycle.py`
- `theme/dialog/match_result_dialog.py`

### Change 1 — an `edit_result` event through the view

Follow the existing `assign_stations` wiring exactly — it is the closest analogue.

- `theme/tables/match.py`: add `on_edit_result=None` to `__init__`, store it, and
  wire `self.table.on('edit_result', lambda event: self._bg(self._handle_edit_result(event)))`
  inside the `if self.admin_controls:` block, guarded by
  `if self.on_edit_result is not None:`.
- `theme/tables/match_handlers.py`: add the mirror handler beside
  `_handle_assign_stations`:

  ```python
      async def _handle_edit_result(self, event):
          match_id = self._event_match_id(event)
          if match_id is not None and self.on_edit_result:
              await self.on_edit_result(match_id)
  ```
- `theme/tables/match_grid.py`: add `edit_result -> { key: props.row.id }` to the
  frozen event-contract list in the module docstring.

### Change 2 — the control

`theme/tables/match_slots.py`, `STATE_SLOT`, in the `Finished` branch you edited
in T1.2 — add a secondary action beside Confirm, crud-only:

```html
        <q-btn v-if="__CC__" @click="$parent.$emit('edit_result', props)"
               icon="edit" size="sm" flat dense color="primary">
            <q-tooltip>Change the recorded winner</q-tooltip>
        </q-btn>
```

`theme/tables/match_grid.py`, `_ACTIONS` — the mobile mirror, emitting
`{ key: props.row.id }`.

### Change 3 — an edit mode on the result dialog

`theme/dialog/match_result_dialog.py`. Add `mode: str = 'record'` to
`__init__`. In `'edit'` mode:

- the header reads `Change result — Match #{id}`
- a caption above the buttons names the current winner:
  `Currently recorded: {name}`
- the current winner's button renders `outline` and the other renders solid, so
  the tap that changes something is the prominent one
- the success toast reads `Result changed: {name} wins.`

Behaviour is otherwise identical — `_submit_winner` calls the same service.

### Change 4 — wire it, without re-finishing

`theme/tables/match_lifecycle.py`, add a crud-only handler. **Critically, its
`on_submit` must not call `finish_match`** — the match is already finished:

```python
    async def on_edit_result(self, match_id: int):
        match = await Match.get(
            id=match_id, tenant_id=require_tenant_id(),
        ).prefetch_related('players', 'players__user')

        async def after_edit(_):
            await self.table_view.update_row_by_id(match_id)

        with self.page_container:
            dialog = MatchResultDialog(match=match, on_submit=after_edit, mode='edit')
            await dialog.open()
```

and add `cb['on_edit_result'] = self.on_edit_result` to the `if self.can_crud:`
branch of `callbacks()`.

A settled bracket game raises `ValueError` from `assert_bracket_result_editable`;
`_submit_winner` already routes that through `notify_error`, which shows the
"Correct it from the bracket (Results → Override)" message. That is the intended
behaviour — do not weaken the guard.

### Tests

`tests/services/test_match_service.py`:

```python
async def test_result_can_be_re_recorded_for_a_non_bracket_match(db)
async def test_re_recording_swaps_the_ranks(db)
async def test_re_recording_a_settled_bracket_game_raises(db)   # may already exist
```

### Verify

As `staff_user`, on a Finished non-bracket match: the pencil appears beside
Confirm, the dialog opens naming the current winner, tapping the other player
swaps the emphasis on the row and writes a `match.result_recorded` audit row.
On a Finished **bracket** match, expect the amber "Correct it from the bracket"
toast and no change. Confirm the pencil does **not** appear for `proctor_user`.

---

## T4.3 — Refuse to confirm a match with no recorded result

**Why.** `confirm_match`'s `check()` only asserts `finished_at` is set. A match
with no `finish_rank` on any player confirms happily and advances the bracket on
an empty result. The UI path happens to always record first, but the REST
`/finish` route does not, and nothing enforces the invariant.

### Files

- `application/services/match/match_schedule_service.py`

### Change

`confirm_match` (~line 227). `check()` is synchronous and runs before
`_transition` fetches relations, so load players first:

```python
    async def confirm_match(self, match: Match, actor: Optional[User] = None) -> None:
        await match.fetch_related('players')

        def check() -> None:
            if not match.finished_at:
                raise ValueError("Match must be finished before confirming")
            if match.confirmed_at:
                raise ValueError("Match is already confirmed")
            if not any(p.finish_rank for p in match.players):
                raise ValueError(
                    "No result has been recorded for this match — record the "
                    "winner before confirming."
                )
        await self._transition(
            match, actor,
            action_verb="confirm",
            check=check,
            timestamp_field="confirmed_at",
            audit_action=AuditActions.MATCH_CONFIRMED,
            event_type=EventType.MATCH_CONFIRMED,
            build_message=lambda m, c, b: _state_notification(m, c, "Confirmed", b),
            authorize=AuthService.can_confirm_match,   # from T1.1
        )
        ...
```

Leave the Challonge push and bracket advance below it untouched.

### Tests

`tests/services/test_match_status.py`:

```python
async def test_confirm_rejects_a_match_with_no_result(db)
async def test_confirm_accepts_a_match_with_a_winner(db)
```

Check whether any existing test confirms a result-less match — if one does, it was
asserting the bug; update it and say so in the commit message.

### Verify

`POST /api/v1/matches/{id}/confirm` on a finished-but-result-less match must
return 400 with that message. Seed one such match in `scripts/seed_dev.py` if none
exists, so the state is reachable in the browser.

---

## T4.4 — A dispute signal the proctor can set and the admin resolves

**Depends on:** T4.1, T4.2.

**Why.** There is no dispute concept anywhere — grep finds nothing, and
`scripts/seed_dev.py` fakes its "Disputed Match" as simply
finished-and-not-confirmed. The agreed model is *the proctor records their best
guess and the admin overrides during confirmation*; without a flag the admin has
no signal distinguishing a routine result from a contested one.

Keep this narrow. It is a **flag plus a note**, not a workflow. Do not build
states, assignment, threads, or notifications beyond the event.

### Step 1 — model

`models/match.py`, on `Match`:

```python
    # Proctor-set "an admin should look at this before confirming" flag, with the
    # proctor's own words. Cleared when the admin confirms — confirming *is* the
    # resolution. Deliberately not a state: the match is still Finished.
    needs_review = fields.BooleanField(default=False)
    review_note = fields.TextField(null=True)
```

```bash
poetry run aerich migrate --name add_match_needs_review
poetry run aerich upgrade
```

No new model, so `check_seed_coverage.py` will not fire — but still seed the state
(step 6).

### Step 2 — audit actions and events

`application/services/audit_service.py`, in `AuditActions` beside the other
`MATCH_*` entries:

```python
    MATCH_FLAGGED_FOR_REVIEW = 'match.flagged_for_review'
    MATCH_REVIEW_CLEARED = 'match.review_cleared'
```

These **do** warrant events — a contested result is exactly what an alerting
webhook wants. Add mirror members to `EventType` **and** to `EventType.ALL` in
`application/events/event_types.py`. `EventType` is an external contract: add,
never rename.

### Step 3 — service

`application/services/match/match_service.py`:

```python
    async def flag_for_review(self, match_id: int, note: Optional[str], actor: User) -> Match:
        """Mark a recorded result as needing an admin's eyes before confirmation."""
        match = await self._require_match(match_id)
        await AuthService.ensure(
            await AuthService.can_run_match(actor, match),
            f"User cannot flag match {match_id} for review",
        )
        if not match.finished_at:
            raise ValueError("Only a finished match can be flagged for review.")

        match.needs_review = True
        match.review_note = (note or '').strip() or None
        await match.save()

        await self.audit_service.write_and_publish(
            actor, AuditActions.MATCH_FLAGGED_FOR_REVIEW,
            {'match_id': match.id, 'note': match.review_note},
            EventType.MATCH_FLAGGED_FOR_REVIEW,
            event_extra={'tournament_id': match.tournament_id},
        )
        match_live.publish(match.id)
        return match
```

Add `clear_review(match_id, actor)` on the same shape, gated on
`can_confirm_match` (clearing is the admin's call), writing
`MATCH_REVIEW_CLEARED`.

Use `write_and_publish` — `check_dry_regressions.py` blocks a hand-rolled
`write_log` + `event_bus.publish` pair.

### Step 4 — confirming resolves it

`application/services/match/match_schedule_service.py`, `confirm_match`, after the
`_transition` call succeeds and before the Challonge/bracket enqueues:

```python
        if match.needs_review:
            match.needs_review = False
            await match.save()
```

Do **not** clear `review_note` — the note is the record of why it was flagged, and
the audit row already carries it. Confirming a flagged match should include the
note in its audit details so the trail reads end to end; pass
`details={'match_id': ..., 'resolved_review_note': match.review_note}` if you can
do so without disturbing `_transition`'s shared shape, otherwise write a separate
`MATCH_REVIEW_CLEARED` row.

### Step 5 — UI

**Proctor sets it.** `theme/dialog/match_result_dialog.py`, below the winner
buttons:

```python
                flag = ui.checkbox('Flag for admin review')
                note = ui.textarea(label='What happened?').props('outlined dense autogrow') \
                    .classes('full-width')
                note.bind_visibility_from(flag, 'value')
```

In `_submit_winner`, after `record_match_result` succeeds and before `on_submit`:

```python
            if flag.value:
                await self.match_service.flag_for_review(self.match.id, note.value, actor)
```

**Everyone sees it.** `application/services/match/match_display_service.py`, in
`_format_match_for_display`:

```python
            'needs_review': match.needs_review,
            'review_note': match.review_note or '',
```

`theme/tables/match_slots.py`, in the `STATE_SLOT` `Finished` branch, above the
Confirm button:

```html
        <span v-if="props.row.needs_review" class="wiz-chip wiz-chip--pending">
            <q-icon name="report_problem" size="14px" />Needs review
            <q-tooltip v-if="props.row.review_note">{{ props.row.review_note }}</q-tooltip>
        </span>
```

Mirror it on the mobile card (`theme/tables/match_grid.py`, `_ACTIONS`, or as its
own `mgc-detail` row so the note is readable rather than tooltip-only — a tooltip
is useless on a touch screen, so on mobile render the note as text).

**Admin's queue.** Extend the T4.1 `review_queue` strip: count flagged matches
separately and give them a distinct chip, since a flagged result needs attention
before an unflagged one.

### Step 6 — REST

`api/schemas/matches.py` — add `needs_review: bool = False` and
`review_note: Optional[str] = None` to `MatchResponse`.

`api/routers/match_actions.py` — a new route beside `/result`:

```python
@router.post("/{match_id}/review", response_model=MatchResponse, summary="Flag or clear a result review")
async def set_review(match_id: int, body: SetReviewRequest, actor: User = Depends(require_write_actor)):
    service = MatchService()
    if body.needs_review:
        await service.flag_for_review(match_id, body.note, actor=actor)
    else:
        await service.clear_review(match_id, actor=actor)
    return await load_match_response(match_id)
```

with `SetReviewRequest(needs_review: bool, note: Optional[str] = None)` in
`api/schemas/match_actions.py`.

### Step 7 — seed

`scripts/seed_dev.py` — the existing `disputed_match` (~line 323) is finished and
unconfirmed. Actually flag it:

```python
        if not disputed_match.needs_review:
            disputed_match.needs_review = True
            disputed_match.review_note = (
                "Player Two says the timer was still running when Player Three "
                "raised their hand. Needs an admin to look at the VOD."
            )
            await disputed_match.save()
```

Leave the variable name — it finally means what it says.

### Tests

`tests/services/test_match_service.py`:

```python
async def test_flag_for_review_requires_a_finished_match(db)
async def test_flag_for_review_stores_the_note(db)
async def test_proctor_can_flag_but_not_clear(db)
async def test_confirming_clears_the_flag(db)
async def test_confirming_keeps_the_note(db)
```

`tests/services/test_event_audit_parity.py` passes automatically once both
`EventType` members are added — if it fails, you added the audit action without
the event.

`tests/api/` — round-trip `POST /matches/{id}/review` and assert the fields come
back on `GET /matches/{id}`.

### Docs

- `docs/reference/data-model.md` — the two new `Match` fields and the rule that
  confirming clears the flag.
- `docs/reference/rest-api.md` — the `/review` route and the response fields.
- `docs/features/match-participation.md` — the dispute flow, end to end.
- `docs/features/webhooks.md` if it enumerates event types — add the two.

### Verify

As `proctor_user`, finish a match with the flag ticked and a note. The row must
show "Needs review" with the note reachable. As `staff_user`, the admin board's
queue must call it out; confirming must clear the chip and leave an audit trail
containing the note. Check the mobile card renders the note as text, not a
tooltip.

---

## T4.5 — Show whether the seed actually reached the players

**Why.** Seeds reach players by DM, and `_send_seed_dms`
(`application/services/match/match_schedule_service.py` ~line 343) skips any
player with `dm_notifications` off or no `discord_id`, logging a warning and
nothing else. The proctor — whose step 3 is making sure the players have their
seed — sees only that a URL exists.

**Scope note.** This reports *deliverability*, not delivery: it says who cannot
receive a DM, computed from data already on `User`. Persisting an actual
per-recipient delivery result would need a new model and a change to the fire-and-
forget queue; that is deliberately out of scope. Say so in the tooltip copy so the
UI does not overclaim.

### Files

- `application/services/match/match_display_service.py`
- `theme/tables/match_slots.py`, `theme/tables/match_grid.py`

### Change 1 — the row data

In `_format_match_for_display`, add:

```python
            # Players who cannot receive the seed DM (no linked Discord account,
            # or DMs opted out). Deliverability, not delivery — see T4.5.
            'seed_dm_blocked': [
                p.user.preferred_name for p in match.players
                if not (p.user.discord_id and p.user.dm_notifications)
            ],
```

`players__user` is already prefetched by `get_all(prefetch_relations=True)`, so
this costs no extra query.

### Change 2 — the indicator

`theme/tables/match_slots.py`, `SEED_SLOT`, inside the `<span v-if="props.value">`
branch (so it only shows once a seed exists):

```html
        <q-icon v-if="props.row.seed_dm_blocked && props.row.seed_dm_blocked.length"
                name="notifications_off" class="st-pending q-ml-xs" size="xs">
            <q-tooltip>Not DM-able: {{ props.row.seed_dm_blocked.join(', ') }} — hand them the seed</q-tooltip>
        </q-icon>
```

Mirror it in `theme/tables/match_grid.py`, `_SEED_DETAIL`, rendering the names as
text rather than a tooltip for touch.

### Tests

`tests/services/test_match_display_service.py`:

```python
async def test_seed_dm_blocked_lists_a_player_with_dms_off(db)
async def test_seed_dm_blocked_lists_a_player_with_no_discord_id(db)
async def test_seed_dm_blocked_is_empty_when_everyone_is_reachable(db)
```

### Verify

Set `dm_notifications=False` on one seeded player, reload the proctor board, and
confirm the icon appears beside a generated seed and names that player.

---

## Wave 4 wrap-up

```bash
poetry run pytest
scripts/ui_flag_sweep.sh
```

Browser-verify as both `proctor_user` and `staff_user` at 1500px and 430px, and
walk the full loop once by hand:

1. `proctor_user` checks a match in, seats both players, rolls the seed, starts it.
2. Records a winner **with** the review flag and a note.
3. `staff_user` sees it in the review queue, opens the pencil, changes the winner.
4. Confirms — the flag clears, the bracket advances, the audit log shows
   `match.result_recorded` → `match.flagged_for_review` → `match.confirmed`.

That end-to-end pass is the real acceptance test for the whole plan. If any step
is awkward, note it rather than papering over it — the point of the plan was the
workflow, not the diff.

Suggested PR split: *"Surface the admin's result-review queue"* (T4.1),
*"Let admins correct a recorded result"* (T4.2, T4.3), *"Add a dispute flag to
match results"* (T4.4), *"Show seed DM deliverability"* (T4.5).
