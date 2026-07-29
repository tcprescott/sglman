# Wave 1 — close the role boundary

**Read [README.md](README.md) first.** Ground rules and the verification loop are
there and are not repeated here.

Wave 1 is small, mechanical, and entirely about stopping the tool from letting a
proctor perform the admin's step — plus four cheap fixes to controls that are
offered where they cannot work. No new models, no migrations, no new pages.

| Task | Fixes | Depends on |
|---|---|---|
| T1.1 | F1 | — |
| T1.2 | F1 | T1.1 |
| T1.3 | F7 | — |
| T1.4 | F8 | — |
| T1.5 | F9 | — |

---

## T1.1 — Split `can_transition_match` into `can_run_match` and `can_confirm_match`

**Why.** One predicate currently authorises seat / start / finish / record-result
/ roll-seed / assign-stations **and confirm**, and it admits `Role.PROCTOR`. So a
proctor can confirm a match, which fires `ChallongeService.push_result_if_linked`
and `BracketService.advance_if_linked`. Hiding the button is not enough — the
REST route `POST /api/v1/matches/{id}/confirm` authorises through the same
predicate.

### Files

- `application/services/auth_service.py`
- `application/services/match/match_schedule_service.py`
- `application/services/match/match_service.py`
- `tests/services/conftest.py`
- `tests/services/test_auth_service.py`
- `docs/reference/authentication.md`

### Change 1 — the predicates

In `application/services/auth_service.py`, **replace** `can_transition_match`
(currently at ~line 202) with two methods. Delete the old one; do not keep it as
an alias — a stale alias is exactly how this regresses.

```python
    @staticmethod
    async def can_run_match(user: Optional[User], match: Match) -> bool:
        """Run a match on the floor: seat, start, finish, record the result,
        roll its seed, assign stations.

        Admits PROCTOR — this is the proctor's whole job. Confirming is
        deliberately *not* here; see ``can_confirm_match``.
        """
        if await AuthService.is_staff(user) or await AuthService.is_proctor(user):
            return True
        return await AuthService.is_tournament_admin(user, match.tournament_id)

    @staticmethod
    async def can_confirm_match(user: Optional[User], match: Match) -> bool:
        """Officially record a result — staff or the tournament's admin only.

        Excludes PROCTOR by design: confirming advances the native bracket and
        pushes to Challonge, which is the admin's verification step. A proctor's
        workflow ends at recording the winner.
        See docs/reviews/2026-07-proctor-workflow-ux-audit.md (F1).
        """
        if await AuthService.is_staff(user):
            return True
        return await AuthService.is_tournament_admin(user, match.tournament_id)
```

### Change 2 — `MatchScheduleService._transition` takes the gate

`_transition` (~line 130) is shared by seat / start / finish / confirm, so it
cannot hard-code one predicate. Add an `authorize` keyword.

Replace the signature's closing lines and the first two statements of the body:

```python
    async def _transition(
        self,
        match: Match,
        actor: Optional[User],
        *,
        action_verb: str,
        check: Callable[[], None],
        timestamp_field: str,
        audit_action: str,
        event_type: str,
        build_message: Callable[[Match, str, str], tuple],
        authorize: Optional[Callable] = None,
    ) -> None:
```

and

```python
        gate = authorize or AuthService.can_run_match
        await AuthService.ensure(
            await gate(actor, match),
            f"User cannot {action_verb} match {match.id}",
        )
        check()
```

Then in `confirm_match` (~line 227), add `authorize=AuthService.can_confirm_match`
to its `self._transition(...)` call. Leave `seat_match`, `start_match` and
`finish_match` alone — they inherit the `can_run_match` default.

Update `_transition`'s docstring to say the default gate is `can_run_match` and
that `confirm_match` overrides it.

### Change 3 — the three remaining callers

Rename `AuthService.can_transition_match` → `AuthService.can_run_match` at:

- `application/services/match/match_schedule_service.py` ~line 299 (`generate_seed`)
- `application/services/match/match_service.py` ~line 567 (`assign_stations`)
- `application/services/match/match_service.py` ~line 645 (`record_match_result`)

Confirm with `grep -rn can_transition_match --include=*.py .` that nothing
outside `tests/` still references it.

### Change 4 — the test bypass fixture

`tests/services/conftest.py` line 15 lists `'can_transition_match'` in
`_ALLOW_GATES`. Replace that single entry with both new names:

```python
    'can_run_match',
    'can_confirm_match',
```

Leaving the stale name would silently stop bypassing the gate and break unrelated
service tests.

### Tests

Update the existing references in `tests/services/test_auth_service.py`
(lines ~179, ~210, ~217, ~225, ~231) from `can_transition_match` to
`can_run_match`, and rename the `TestCrudVsTransition` class to `TestRunVsCrud`.
Then add a new class beneath it:

```python
class TestRunVsConfirm:
    """A proctor runs matches; only staff / the tournament's admin confirms."""

    async def test_proctor_can_run_but_not_confirm(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.PROCTOR})
        patch_tournament_membership()          # not TA of anything
        match = make_match()
        assert await AuthService.can_run_match(make_user(), match) is True
        assert await AuthService.can_confirm_match(make_user(), match) is False

    async def test_staff_can_confirm(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.STAFF})
        patch_tournament_membership()
        assert await AuthService.can_confirm_match(make_user(), make_match()) is True

    async def test_ta_can_confirm_own_tournament(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership(admin_of={100})
        assert await AuthService.can_confirm_match(make_user(), make_match(tournament_id=100)) is True

    async def test_ta_cannot_confirm_other_tournament(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership(admin_of={100})
        assert await AuthService.can_confirm_match(make_user(), make_match(tournament_id=200)) is False
```

Add a service-level test to `tests/services/test_match_status.py` proving the
gate actually bites through `confirm_match`. That module may apply `bypass_auth`
at module scope, so re-patch the specific gate in-test (which wins):

```python
async def test_proctor_cannot_confirm_match(db, monkeypatch):
    from application.services import auth_service

    async def deny(*_a, **_kw):
        return False
    monkeypatch.setattr(auth_service.AuthService, 'can_confirm_match', deny)

    match = await make_finished_match()          # use the module's existing helper
    with pytest.raises(PermissionError):
        await MatchScheduleService().confirm_match(match, actor=proctor)
    await match.refresh_from_db()
    assert match.confirmed_at is None
```

Add a REST test to `tests/api/test_admin_writes.py` (it already builds
proctor-role tokens — follow the existing pattern in that file):

```python
async def test_proctor_token_cannot_confirm(db, app):
    _, raw = await create_user_token(roles=[Role.PROCTOR])
    match = await make_finished_match()
    async with client_for(app, raw) as c:
        resp = await c.post(f'/api/v1/matches/{match.id}/confirm')
    assert resp.status_code == 403
```

Also assert a proctor token **still gets 200** on `/seat`, `/start`, `/finish`,
`/result`, `/stations` and `/seed` — the point is to narrow one capability, not
all six.

### Docs

`docs/reference/authentication.md` — find the `AuthService` predicate table and
the role matrix, replace the `can_transition_match` row with the two new
predicates, and state explicitly that PROCTOR is excluded from
`can_confirm_match` and why.

### Verify

```bash
poetry run pytest tests/services/test_auth_service.py tests/services/test_match_status.py tests/api/
grep -rn "can_transition_match" --include=*.py .        # expect no hits
```

### Done when

`grep` finds no `can_transition_match` anywhere, a `Role.PROCTOR` actor gets
`PermissionError`/403 from `confirm_match` and 200 from every other lifecycle
action, and the whole suite is green.

---

## T1.2 — Hide the Confirm button from anyone without `can_crud`

**Depends on:** T1.1 (otherwise the button is hidden but the API is still open).

**Why.** `pages/admin_tabs/admin_schedule.py` passes `on_confirm` unconditionally,
unlike `on_edit` and `on_edit_stream_room` which are both `… if can_crud else
None`. The proctor tab constructs the same page with `can_crud=False`.

### Files

- `pages/admin_tabs/admin_schedule.py`
- `theme/tables/match_slots.py`
- `theme/tables/match_grid.py`

### Change 1 — stop wiring the callback

`pages/admin_tabs/admin_schedule.py`, in the `MatchTableView(...)` construction
(~line 213):

```python
            on_confirm=on_confirm if can_crud else None,
```

`want_state_slot` in `theme/tables/match.py` is
`admin_controls and (on_seat or on_start or on_finish or on_confirm)` — the other
three are still non-`None`, so the state slot still registers. No change needed
there.

### Change 2 — desktop cell

`theme/tables/match_slots.py`, the `STATE_SLOT` `Finished` branch (~line 126).
Replace the whole `v-else-if="props.value === 'Finished'"` block with:

```html
    <!-- Finished: Confirm for staff/TA; everyone else sees it is awaiting review -->
    <div v-else-if="props.value === 'Finished'" style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
        <q-btn v-if="__CC__" @click="$parent.$emit('confirm', props)"
               icon="check_circle" color="primary" size="sm">
            Confirm
        </q-btn>
        <span v-else class="wiz-chip wiz-chip--pending">
            <q-icon name="flag" size="14px" />Awaiting confirmation
            <q-tooltip>Recorded. An admin confirms the result.</q-tooltip>
        </span>
        <div style="display: flex; align-items: center; gap: 4px;">
            <q-icon name="flag" class="st-pending" size="xs" />
            <span class="cell-timestamp">{{ props.row.state_timestamp }}</span>
        </div>
    </div>
```

### Change 3 — mobile card

`theme/tables/match_grid.py`, in `_ACTIONS` (~line 183). Change the Finished
button's condition and add a sibling note:

```html
            <q-btn v-else-if="__IA__ && __CC__ && props.row.state === 'Finished'" icon="check_circle" color="primary" size="md"
                   @click="$parent.$emit('confirm', { key: props.row.id })">Confirm</q-btn>
            <span v-else-if="__IA__ && props.row.state === 'Finished'" class="wiz-chip wiz-chip--pending">
                <q-icon name="flag" size="14px" />Awaiting confirmation</span>
```

Leave the `.mgc-actions` wrapper's `v-if` alone — `'Finished'` must stay in its
`includes([...])` list so the note renders.

### Verify

Screenshot the proctor board with `Finished` added to the State filter (see the
README loop; you will need a one-off Playwright script to open the filter) and
confirm the Confirm button is gone and "Awaiting confirmation" shows. Then do the
same as `staff_user` on `/admin/schedule` and confirm the button is still there.
Check both at 1500px and 430px.

### Done when

`proctor_user` sees no Confirm control on either layout; `staff_user` sees it on
both; no console errors.

---

## T1.3 — Use preferred names (and non-destructive styling) in the lifecycle confirmations

**Why.** `admin_schedule.py` builds the start and confirm dialog messages from
`p.user.username`, so the proctor reads *"…start match ID 2? player_one,
player_two"* while the table behind says "Player One" / "Player Two". This lands
exactly when they are identity-checking two humans. The generic
`ConfirmationDialog` also styles its button `color=negative` (red) — destructive
semantics on starting a match.

### Files

- `pages/admin_tabs/admin_schedule.py`
- `theme/dialog/confirmation_dialog.py`

### Change 1 — names

`pages/admin_tabs/admin_schedule.py`, in `on_start` (~line 100) and `on_confirm`
(~line 152), replace both occurrences of:

```python
            player_names = ', '.join(
                [p.user.username for p in match.players])
```

with:

```python
            player_names = ', '.join(
                [p.user.preferred_name or p.user.username for p in match.players])
```

While there, make the start message name the action rather than the id. In
`on_start`:

```python
                dialog = ConfirmationDialog(
                    message=f'Start match #{match.id}?\n\n{player_names}',
                    confirm_text='Start match',
                    tone='primary',
                    on_confirm=handle_confirm,
                )
```

and in `on_confirm`:

```python
                dialog = ConfirmationDialog(
                    message=f'Confirm the recorded result for match #{match.id}?\n\n{player_names}',
                    confirm_text='Confirm result',
                    tone='primary',
                    on_confirm=handle_confirm,
                )
```

### Change 2 — an opt-in tone on the shared dialog

`theme/dialog/confirmation_dialog.py`. Add a `tone` parameter defaulting to
`'negative'` so **every existing caller keeps its current red button** and only
the two above opt into primary:

```python
class ConfirmationDialog:
    def __init__(self, message: str = "Are you sure?", on_confirm=None,
                 confirm_text="Confirm", cancel_text="Cancel", tone: str = "negative"):
        ...
        self.tone = tone
```

and in `open()`, replace both `.props('color=negative')` with
`.props(f'color={self.tone}')`.

Do **not** flip the default — other callers are genuine deletes.

### Tests

`tests/theme/` holds the presentation tests. Add
`tests/theme/test_confirmation_dialog_tone.py` asserting the default is
`negative` and that `tone='primary'` is honoured. If driving NiceGUI in a test is
awkward in this repo, assert on the constructor state (`dialog.tone`) instead —
the point is to lock the default.

### Verify

Open the Start dialog as `proctor_user` and read the text back; it must show
"Player One, Player Two" and a gold/primary button.

---

## T1.4 — Stop offering seed generation on racetime.gg matches

**Why.** The lifecycle and station controls both check `props.row.is_racetime`;
the seed Generate button does not, so a proctor is invited to roll a seed for a
match whose race room owns the seed.

### Files

- `theme/tables/match_slots.py`
- `theme/tables/match_grid.py`

### Change 1 — desktop

`theme/tables/match_slots.py`, `SEED_SLOT` (~line 70). Change:

```html
    <q-btn v-if="props.row.tournament_seed_generator && !props.value"
```

to:

```html
    <q-btn v-if="props.row.tournament_seed_generator && !props.value && !props.row.is_racetime"
```

Leave the `<span v-if="props.value">` link branch alone — an already-generated
seed should still display.

### Change 2 — mobile

`theme/tables/match_grid.py`, `_SEED_DETAIL` (~line 149). Change the button's
condition the same way:

```html
                <q-btn v-if="__IA__ && props.row.tournament_seed_generator && !props.row.generated_seed && !props.row.is_racetime"
```

Also tighten the outer row's `v-if` (~line 146) so the whole detail row collapses
rather than rendering an empty "Seed" label:

```html
        <div class="mgc-detail" v-if="props.row.generated_seed || (__IA__ && props.row.tournament_seed_generator && !props.row.is_racetime)">
```

### Verify

The seeded `default` tenant has racetime matches (ids 1, 6, 7, 9, 10).
Screenshot the proctor board at both widths: those rows must show the seed value
if one exists and **no** Generate button, while the non-racetime rows (2, 3, 5,
11) still offer it.

---

## T1.5 — Do not offer (or allow) check-in on a match with no players

**Why.** Bracket-scheduled matches whose entrants are not yet resolved (seeded
ids 12, 13) render a Check In button over an empty Players cell. Following it
opens a station dialog that says "No players assigned to this match" and still
submits, seating a match with nobody in it — `seat_match` has no player
precondition.

### Files

- `application/services/match/match_schedule_service.py`
- `theme/tables/match_slots.py`
- `theme/tables/match_grid.py`

### Change 1 — the service guard (this is the enforcement)

`application/services/match/match_schedule_service.py`, `seat_match` (~line 174).
`_transition`'s `check()` is synchronous and runs *before* the relations are
fetched, so `seat_match` must load players itself first:

```python
    async def seat_match(self, match: Match, actor: Optional[User] = None) -> None:
        await match.fetch_related('tournament', 'players')
        if match.tournament and match.tournament.is_racetime_enabled:
            raise ValueError(
                "Check-in is disabled for racetime.gg tournaments — the race "
                "room manages the match lifecycle."
            )

        def check() -> None:
            if not match.players:
                raise ValueError(
                    "This match has no players yet — nothing to check in."
                )
            if match.seated_at:
                raise ValueError("Match is already checked in")
        await self._transition(...)   # unchanged
```

`fetch_related` on an already-prefetched relation is a no-op, so the UI callers
that already prefetch are unaffected, and the REST route (which does not) is now
covered.

### Change 2 — hide the button

`theme/tables/match_slots.py`, `STATE_SLOT` Scheduled branch (~line 91):

```html
        <q-btn v-if="!props.row.is_racetime && props.row.players && props.row.players.length"
               @click="$parent.$emit('seat', props)"
               icon="chair" color="primary" size="sm">
            Check In
        </q-btn>
        <span v-else-if="!props.row.is_racetime" class="st-neutral italic-note">
            awaiting players
            <q-tooltip>This match has no players yet</q-tooltip>
        </span>
        <span v-else class="st-neutral italic-note">
            racetime.gg
            <q-tooltip>Managed by the racetime.gg room</q-tooltip>
        </span>
```

Note the ordering: the existing racetime `<span v-else>` becomes `v-else` after a
new `v-else-if`, so the three cases stay mutually exclusive.

### Change 3 — mobile mirror

`theme/tables/match_grid.py`, `_ACTIONS` (~line 175). Apply the same three-way
split to the Scheduled branch:

```html
            <q-btn v-if="__IA__ && props.row.state === 'Scheduled' && !props.row.is_racetime && props.row.players && props.row.players.length"
                   icon="chair" color="primary" size="md"
                   @click="$parent.$emit('seat', { key: props.row.id })">Check In</q-btn>
            <div v-else-if="__IA__ && props.row.state === 'Scheduled' && !props.row.is_racetime" class="st-neutral italic-note">
                Awaiting players</div>
            <div v-else-if="__IA__ && props.row.state === 'Scheduled' && props.row.is_racetime" class="st-neutral italic-note">
                Managed by racetime.gg</div>
```

### Tests

`tests/services/test_match_service.py` (or `test_match_status.py`, wherever the
existing seat tests live — find them with `grep -rn "seat_match" tests/`):

```python
async def test_seat_match_rejects_player_less_match(db):
    match = await make_match(players=[])
    with pytest.raises(ValueError, match='no players'):
        await MatchScheduleService().seat_match(match, actor=staff)
    await match.refresh_from_db()
    assert match.seated_at is None
```

Add the REST mirror in `tests/api/` asserting `POST /matches/{id}/seat` returns
400 for a player-less match.

### Verify

Rows 12 and 13 on the seeded board must show "awaiting players" instead of a
Check In button, at both widths.

---

## Wave 1 wrap-up

Before opening a PR:

```bash
poetry run pytest
```

Then re-run the browser loop for both `proctor_user` (`/volunteer/proctor-station`)
and `staff_user` (`/admin/schedule`) at 1500px and 430px, and read every
screenshot. Wave 1 touches slot templates that four other pages share — the home
schedule board and the player dashboard embed `MatchTableView` too, so confirm
`/` and `/home/player` still render.

Commit as one PR titled *"Keep match confirmation to admins and fix impossible
proctor controls"*, describing the behaviour change (a proctor can no longer
confirm) rather than the file list.
