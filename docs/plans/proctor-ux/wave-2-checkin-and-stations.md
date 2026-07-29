# Wave 2 — make check-in honest and stations real

**Read [README.md](README.md) first.** **Wave 1 must be merged** — T2.2 relies on
`can_run_match` already admitting proctors.

Wave 2 fixes the two places where the tool silently does something other than
what its labels say: the Check In button that never mentions check-in, and the
station field that accepts anything including a station two people are already
sitting at.

| Task | Fixes | Depends on | Size |
|---|---|---|---|
| T2.1 | F3 | — | small |
| T2.2 | F5 | T1.1 | tiny |
| T2.3 | F4 | — | **large** — new model + migration |
| T2.4 | F2 (partial) | T2.3 | tiny |

Do T2.1, T2.2 and T2.4 in one PR and T2.3 in its own — T2.3 carries a migration
and should be reviewable alone.

---

## T2.1 — Say "check in" when checking in

**Why.** Clicking **Check In** opens a dialog titled *"Assign Stations - Match
#11"*, body header *"Assign Stations to Players:"*, primary button *"Assign
Stations"*. The word check-in appears nowhere. On submit the only feedback is
*"Stations assigned successfully for match #11"* — the seat happens afterwards in
`confirm_seating`, which notifies nothing. Verified live: the row moves
`Scheduled → Checked In` and the proctor is never told.

The same dialog is legitimately reused for re-assigning stations on an
already-seated match, so it needs two modes, not a rename.

### Files

- `theme/dialog/station_assignment_dialog.py`
- `pages/admin_tabs/admin_schedule.py`

### Change 1 — a `purpose` mode on the dialog

`theme/dialog/station_assignment_dialog.py`. Add a keyword-only `purpose` to
`__init__`, defaulting to the existing behaviour:

```python
# Copy for the dialog's two jobs. 'checkin' is the proctor's combined
# step 1 + 2 (seat the players, then check the match in); 'stations' is
# correcting the seating of a match that is already checked in.
_PURPOSE_COPY = {
    'checkin': {
        'title': 'Check in — Match #{id}',
        'lead': 'Seat each player at a station, then check the match in.',
        'submit': 'Check in & seat',
    },
    'stations': {
        'title': 'Assign stations — Match #{id}',
        'lead': 'Update the station each player is sitting at.',
        'submit': 'Save stations',
    },
}


class StationAssignmentDialog:
    def __init__(self, match: Match, on_submit: Optional[Callable] = None,
                 *, purpose: str = 'stations'):
        ...
        self.purpose = purpose if purpose in _PURPOSE_COPY else 'stations'
```

In `open()`, replace the hard-coded strings:

- header label (~line 53): `_PURPOSE_COPY[self.purpose]['title'].format(id=self.match.id)`
- the `'Assign Stations to Players:'` label (~line 75): `_PURPOSE_COPY[self.purpose]['lead']`
- the primary button (~line 99): `ui.button(_PURPOSE_COPY[self.purpose]['submit'], on_click=self._handle_submit).props('color=primary')`

### Change 2 — move the success toast to whoever finished the job

In `_handle_submit` (~line 114), the toast currently fires before the caller has
seated anything. Make the dialog only speak for the case it actually completes:

```python
            await self.match_service.assign_stations(self.match.id, assignments, actor=actor)

            if self.purpose == 'stations':
                ui.notify(f'Stations updated for match #{self.match.id}.', color='positive')

            if self.on_submit:
                await self.on_submit(self.match)

            self.dialog.close()
```

Then in `pages/admin_tabs/admin_schedule.py`, `confirm_seating` (~line 86), notify
after the seat actually succeeds:

```python
        async def confirm_seating(match: Match):
            try:
                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                await match_schedule_service.seat_match(match, actor=actor)
                await table_view.update_row_by_id(match.id)
                with page_container:
                    ui.notify(f'Match #{match.id} checked in.', color='positive')
            except (PermissionError, ValueError) as e:
                with page_container:
                    notify_error(e)
```

Note this also collapses the two existing `except` arms into `notify_error`
(`from theme.notify import notify_error`), per the README's error convention.
Apply the same collapse to `confirm_starting`, `confirm_finishing` and
`confirm_confirming` in the same file while you are here — they are the same
duplicated pair.

### Change 3 — pass the purpose from each entry point

`pages/admin_tabs/admin_schedule.py`:

- `on_seat` (~line 80): `StationAssignmentDialog(match=match, on_submit=handle_confirm, purpose='checkin')`
- `on_assign_stations` (~line 190): `StationAssignmentDialog(match=match, on_submit=after_assign, purpose='stations')`

### Tests

Presentation copy is not unit-tested in this repo; verify in the browser. Do add
a guard against the two modes drifting — `tests/theme/test_station_dialog_copy.py`:

```python
from theme.dialog.station_assignment_dialog import _PURPOSE_COPY

def test_checkin_copy_mentions_checking_in():
    assert 'check' in _PURPOSE_COPY['checkin']['title'].lower()
    assert 'check' in _PURPOSE_COPY['checkin']['submit'].lower()

def test_station_copy_does_not_claim_to_check_in():
    assert 'check in' not in _PURPOSE_COPY['stations']['submit'].lower()
```

### Verify

One-off Playwright script: log in as `proctor_user`, open
`/t/default/volunteer/proctor-station`, click the first **Check In**, dump
`.q-dialog` innerText. It must read "Check in — Match #11" / "Check in & seat".
Submit it and dump `.q-notification` — it must say "Match #11 checked in."
Then click the stations control on an already-seated row and confirm the other
copy set.

---

## T2.2 — Let proctors correct a station after check-in

**Depends on:** T1.1.

**Why.** The re-assign control is gated on `__IA__ && __CC__` in both layouts, so
it is staff-only — yet `MatchService.assign_stations` authorises through
`can_run_match`, which admits proctors, and `admin_schedule.py` wires the callback
for them. The capability is live and the button is hidden, so a proctor who
mis-seats someone has to find staff.

### Files

- `theme/tables/match_slots.py`
- `theme/tables/match_grid.py`

### Change

`theme/tables/match_slots.py`, `PLAYERS_SLOT` (~line 287). Drop `__CC__`, and add
the player-count guard from T1.5 for the same reason:

```html
        <q-btn v-if="__IA__ && !props.row.is_racetime && props.row.players && props.row.players.length"
               @click="$parent.$emit('assign_stations', props)"
               icon="switch_access_shortcut" color="primary" size="xs" flat round>
            <q-tooltip>Assign stations</q-tooltip>
        </q-btn>
```

`theme/tables/match_grid.py`, `_ACTIONS` (~line 185) — same:

```html
            <q-btn v-if="__IA__ && !props.row.is_racetime && props.row.players && props.row.players.length"
                   icon="switch_access_shortcut" color="primary" size="md" outline
                   @click="$parent.$emit('assign_stations', { row: props.row })">Assign Stations</q-btn>
```

The `.mgc-actions` wrapper's `v-if` includes `(__IA__ && __CC__)` as one of its
disjuncts; add `|| __IA__` is **not** what you want — instead change that clause
to `(__IA__ && !props.row.is_racetime)` so the row shows for a proctor who only
has the stations button.

No service change: `can_run_match` already admits proctors after T1.1.

### Tests

Add to the existing REST tests: a proctor token gets 200 from
`POST /api/v1/matches/{id}/stations`. (This likely already passes — assert it so
the gating cannot silently regress.)

### Verify

As `proctor_user`, an already-checked-in row must show the stations icon; clicking
it must open the dialog in `purpose='stations'` mode and save.

---

## T2.3 — Give stations a real pool, and reject double-booking

**Why.** Stations are a fixed venue-owned pool, but the input is a bare text field
validated only by an optional format regex (`StationFormat` defaults to `FREE`,
i.e. any string ≤ 50 chars). Nothing knows which stations exist or which are
occupied. Verified live: typing `12` into **both** players' fields on one match is
accepted silently — two people sent to one station. The same holds across
concurrent matches.

### Design decisions (do not change these without asking)

- **`MatchPlayers.assigned_station` stays a `CharField`.** It stores the label,
  not an FK. This avoids a data migration over existing rows and keeps the REST
  (`api/schemas/matches.py:48`) and MCP contracts unchanged.
- **The pool is advisory until it exists.** A tenant with **zero** `Station` rows
  keeps today's free-text + regex behaviour exactly. Validation against the pool
  only engages once the tenant has defined stations. This is what lets the change
  ship without breaking other communities.
- **No pairing rule.** Do not compute or suggest opposite-side pairs.
- **Occupancy is derived**, not stored: a station is occupied if some match that
  is seated and not finished has a player assigned to it.

### Files

New:
- `application/repositories/station_repository.py`
- `application/services/station_service.py`
- `tests/tenancy/test_station_tenant_isolation.py`

Modified:
- `models/match.py`, `models/__init__.py`
- `application/repositories/__init__.py`, `application/repositories/match_repository.py`
- `application/services/__init__.py`, `application/services/match/match_service.py`
- `application/services/audit_service.py`
- `theme/dialog/station_assignment_dialog.py`
- `pages/admin_tabs/admin_system_config.py`
- `scripts/seed_dev.py`
- `tests/services/test_match_service.py`, `tests/services/test_event_audit_parity.py`
- `docs/reference/data-model.md`, `docs/reference/services.md`

### Step 1 — the model

`models/match.py`, immediately after `class StreamRoom` (it is the closest
analogue — per-tenant venue infrastructure with a unique name):

```python
class Station(Model):
    """A physical seat/setup in the venue a match player can be assigned to.

    The pool a proctor picks from. ``MatchPlayers.assigned_station`` stores the
    *label*, not an FK: the pool is a picker and a validation source, and a
    community that has defined no stations keeps the historical free-text
    behaviour.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='stations', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=50)
    # Free-text grouping ("North wall", "Row A") shown beside the name in the
    # picker. Purely a label — it carries no pairing semantics.
    section = fields.CharField(max_length=50, null=True)
    sort_order = fields.IntField(default=0)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'station'
        unique_together = (('tenant', 'name'),)
```

Export `Station` from `models/__init__.py` (both the import block and `__all__`,
keeping alphabetical order — it goes next to `StationFormat`).

```bash
poetry run aerich migrate --name add_station_pool
poetry run aerich upgrade
```

Read the generated migration before committing it: it must only `CREATE TABLE
"station"` plus its unique index. If it contains anything else, the working tree
has unrelated model drift — stop and investigate.

### Step 2 — the repository

`application/repositories/station_repository.py`, modelled on
`stream_room_repository.py`:

```python
"""Station Repository - Data Access Layer

Handles database operations for the venue's station pool.
"""

from typing import List

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import scoped
from models import Station


class StationRepository(TenantScopedRepository[Station]):
    """Repository for station pool data access."""

    model = Station

    @staticmethod
    async def get_all() -> List[Station]:
        return await scoped(Station.all()).order_by('sort_order', 'name')

    @staticmethod
    async def get_active() -> List[Station]:
        return await scoped(Station.filter(is_active=True)).order_by('sort_order', 'name')

    @staticmethod
    async def active_names() -> set[str]:
        """The labels a station assignment may use, or an empty set when this
        community has not defined a pool (which keeps free-text behaviour)."""
        return set(await scoped(Station.filter(is_active=True)).values_list('name', flat=True))
```

`create` / `get_by_id` / `update` / `delete` come from `TenantScopedRepository`.
Export `StationRepository` from `application/repositories/__init__.py`.

### Step 3 — occupancy lookup

`application/repositories/match_repository.py`, add:

```python
    @staticmethod
    async def occupied_stations(exclude_match_id: Optional[int] = None) -> dict:
        """``{station label: match id}`` for matches in play right now.

        "In play" is seated-and-not-finished: a station frees up when the match
        at it finishes, not when it is confirmed.
        """
        query = scoped(MatchPlayers.filter(
            assigned_station__isnull=False,
            match__seated_at__isnull=False,
            match__finished_at__isnull=True,
        ))
        if exclude_match_id is not None:
            query = query.exclude(match_id=exclude_match_id)
        rows = await query.values('assigned_station', 'match_id')
        return {r['assigned_station']: r['match_id'] for r in rows if r['assigned_station']}
```

Import `MatchPlayers` in that module if it is not already imported.

### Step 4 — validation in the service

`application/services/match/match_service.py`, `assign_stations` (~line 551).
Replace the single format loop with the full ladder. Order matters — report the
most specific problem first:

```python
        fmt = await SystemConfigService.get_station_format()
        pattern = _STATION_REGEXES[fmt]
        pool = await self.station_repository.active_names()
        occupied = await self.repository.occupied_stations(exclude_match_id=match.id)

        requested = [s for s in assignments.values() if s]

        # 1. Two players of the same match cannot share a station.
        duplicates = {s for s in requested if requested.count(s) > 1}
        if duplicates:
            raise ValueError(
                f"Station {sorted(duplicates)[0]} is assigned to more than one "
                "player in this match."
            )

        for station in requested:
            # 2. Format (unchanged behaviour, and the only check when no pool
            #    is defined).
            if not pattern.fullmatch(station):
                raise ValueError(
                    f"Station '{station}' does not match the required format ({fmt.value})"
                )
            # 3. Must be a real station, once this community has defined any.
            if pool and station not in pool:
                raise ValueError(
                    f"'{station}' is not one of this community's stations."
                )
            # 4. Not already in use by another match in play.
            if station in occupied:
                raise ValueError(
                    f"Station {station} is in use by match #{occupied[station]}."
                )
```

Add `self.station_repository = StationRepository()` to `MatchService.__init__`
alongside the existing repositories, and import it.

### Step 5 — station CRUD service

`application/services/station_service.py`:

```python
"""Station Service - Business Logic Layer

CRUD for the venue's station pool. Staff-only; the pool is community
configuration, not per-match data.
"""

from typing import List, Optional

from application.repositories import StationRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import Station, User


class StationService:
    """Manage the community's station pool."""

    def __init__(self) -> None:
        self.repository = StationRepository()
        self.audit_service = AuditService()

    async def list_stations(self, active_only: bool = False) -> List[Station]:
        return await (self.repository.get_active() if active_only else self.repository.get_all())

    async def create_station(self, name: str, actor: User, *,
                             section: Optional[str] = None, sort_order: int = 0) -> Station:
        await AuthService.ensure(
            await AuthService.is_staff(actor), "Only Staff can manage stations",
        )
        name = (name or '').strip()
        if not name:
            raise ValueError("Station name is required.")
        if name in await self.repository.active_names():
            raise ValueError(f"Station '{name}' already exists.")
        station = await self.repository.create(name=name, section=section, sort_order=sort_order)
        await self.audit_service.write_log(
            actor, AuditActions.STATION_CREATED,
            {'station_id': station.id, 'name': name},
        )
        return station
```

Add `update_station(station_id, actor, **fields)` and `delete_station(station_id,
actor)` on the same shape, writing `STATION_UPDATED` / `STATION_DELETED`.
`delete_station` must **not** cascade into historical `MatchPlayers` rows —
`assigned_station` is a label, so past matches keep their text. Prefer
deactivating (`is_active=False`) over deleting in the UI.

Export `StationService` from `application/services/__init__.py` (import block and
`__all__`).

### Step 6 — audit actions

`application/services/audit_service.py`, in `AuditActions`, beside the existing
`STREAM_ROOM_*` entries:

```python
    STATION_CREATED = 'station.created'
    STATION_UPDATED = 'station.updated'
    STATION_DELETED = 'station.deleted'
```

**These need no `EventType`.** Add all three to `_EVENT_CANDIDATES` in
`tests/services/test_event_audit_parity.py`, right beside the `STREAM_ROOM_*`
entries that are there for exactly the same reason (venue configuration, no
subscriber interest), or that test fails.

### Step 7 — the picker

`theme/dialog/station_assignment_dialog.py`. In `open()`, load the pool once and
branch:

```python
        stations = await StationService().list_stations(active_only=True)
        occupied = await self.match_service.occupied_stations_for_dialog(self.match.id)
```

Add that read-through on `MatchService` (presentation must not touch a repository
directly):

```python
    async def occupied_stations_for_dialog(self, match_id: int) -> dict:
        """``{label: match id}`` for stations in play, excluding this match."""
        return await self.repository.occupied_stations(exclude_match_id=match_id)
```

Then per player, when `stations` is non-empty use a select whose occupied entries
are labelled and disabled; otherwise keep today's `ui.input` untouched:

```python
                            if stations:
                                options = {
                                    s.name: (
                                        f'{s.name} — in use (match #{occupied[s.name]})'
                                        if s.name in occupied
                                        else (f'{s.name} · {s.section}' if s.section else s.name)
                                    )
                                    for s in stations
                                }
                                station_input = ui.select(
                                    options=options, label='Station',
                                    with_input=True, clearable=True,
                                ).props('outlined dense').classes('full-width')
                            else:
                                station_input = ui.input(
                                    label='Station',
                                    placeholder='e.g., A1, B2, Station 3',
                                    validation={'Invalid station format': lambda v: not v or _STATION_REGEXES[fmt].fullmatch(v) is not None},
                                ).props('outlined dense maxlength=50').classes('full-width')
```

Keep pre-filling the player's existing `assigned_station` in both branches — an
already-assigned station must remain selectable even though it shows as occupied
by another match's lookup (it is excluded by `exclude_match_id`, so it will not).

`_handle_submit` needs no change: `station_input.value` is a string either way.
The service is the enforcement; the picker is the affordance.

**While you are here, fix an existing DRY violation:** `_STATION_REGEXES` is
defined identically in `theme/dialog/station_assignment_dialog.py:14-19` and
`application/services/match/match_service.py:44-49`. Move it to
`application/services/match/match_service.py` as the single definition and have
the dialog import it, or lift it to `models/enums.py` beside `StationFormat`.
`check_dry_regressions.py` may flag it otherwise.

### Step 8 — admin surface

Put pool management in the existing **Settings** tab, directly beneath the
"Station Assignment Format" control it belongs with — not a new top-level admin
tab. `pages/admin_tabs/admin_system_config.py` is 156 lines; keep the addition
under ~80 so it stays well inside the 800-line advisory.

Render a compact list of the current stations (name, section, active toggle,
delete) plus an add row (name + section + sort order). Use
`theme/dialog/_helpers.form_dialog` if you reach for a dialog. Every mutation
goes through `StationService`; catch `ValueError`/`PermissionError` and call
`notify_error(e)`.

Because this is a `ui.table` if you build it as one, `check_table_grid.py` will
require a mobile grid — call `enable_mobile_grid(table, columns)` from
`theme.tables.mobile_grid`. A simple `ui.column` of rows avoids that entirely and
is probably the better fit at this size.

### Step 9 — dev seed

`scripts/seed_dev.py`. Add a station block for the `default` tenant, idempotent
and tenant-scoped like its neighbours:

```python
        # Venue station pool — two banks facing into the middle of the room.
        for idx, (name, section) in enumerate(
            [(f'{n}', 'North wall') for n in range(1, 5)]
            + [(f'{n}', 'South wall') for n in range(5, 9)]
        ):
            await Station.get_or_create(
                name=name, tenant=tenant,
                defaults={'section': section, 'sort_order': idx},
            )
```

Then assign two of them to the already-checked-in match so the board shows
stations out of the box, and leave at least one match seated-and-unfinished with
a station so the occupancy check has something to trip on during manual testing.
Seed the `second` tenant with **no** stations, so the free-text fallback path is
exercised too.

`check_seed_coverage.py` blocks the turn if `Station` appears in no seed script,
and `tests/test_seed_coverage.py` asserts a row per tenant-FK model at runtime.

### Tests

`tests/services/test_match_service.py`, a new class:

```python
class TestStationAssignmentValidation:
    async def test_rejects_same_station_twice_in_one_match(self, db):
        match = await make_match_with_two_players()
        with pytest.raises(ValueError, match='more than one player'):
            await MatchService().assign_stations(
                match.id, {p1.id: '3', p2.id: '3'}, actor=staff)

    async def test_rejects_station_outside_the_pool(self, db):
        await Station.create(name='1', tenant_id=1)
        with pytest.raises(ValueError, match='not one of'):
            await MatchService().assign_stations(match.id, {p1.id: '99'}, actor=staff)

    async def test_allows_free_text_when_pool_is_empty(self, db):
        # No Station rows -> historical behaviour, format regex only.
        await MatchService().assign_stations(match.id, {p1.id: 'anything'}, actor=staff)
        await p1.refresh_from_db()
        assert p1.assigned_station == 'anything'

    async def test_rejects_station_in_use_by_a_live_match(self, db):
        other = await make_seated_unfinished_match(station='4')
        await Station.create(name='4', tenant_id=1)
        with pytest.raises(ValueError, match=f'match #{other.id}'):
            await MatchService().assign_stations(match.id, {p1.id: '4'}, actor=staff)

    async def test_frees_the_station_once_the_other_match_finishes(self, db):
        other = await make_finished_match(station='4')
        await Station.create(name='4', tenant_id=1)
        await MatchService().assign_stations(match.id, {p1.id: '4'}, actor=staff)   # no raise

    async def test_reassigning_a_match_to_its_own_station_is_allowed(self, db):
        # exclude_match_id must not make a match collide with itself.
        await MatchService().assign_stations(match.id, {p1.id: '4'}, actor=staff)
        await MatchService().assign_stations(match.id, {p1.id: '4', p2.id: '5'}, actor=staff)
```

`tests/tenancy/test_station_tenant_isolation.py`, following the shape of
`tests/tenancy/test_api_config_tenant_isolation.py`:

- two tenants each define a station named `1`
- `StationRepository.get_all()` inside `tenant_scope(a)` returns only A's
- `active_names()` inside A does not contain B's rows
- assigning station `1` in tenant A is **not** blocked by tenant B's match
  occupying its own station `1`

That last case is the one that actually matters — `occupied_stations` must be
scoped, or two communities running simultaneously would block each other.

### Docs

- `docs/reference/data-model.md` — add `Station` to the model list and the ERD,
  noting that `MatchPlayers.assigned_station` is a label rather than an FK and
  why. The session-start hook reports the model count; update it if the doc
  states one.
- `docs/reference/services.md` — add `StationService`.
- `docs/features/match-participation.md` — describe the station pool and the
  occupancy rule in the check-in section.

### Verify

```bash
poetry run pytest tests/services/test_match_service.py tests/tenancy/ tests/test_seed_coverage.py
```

Then, in the browser as `proctor_user`: open Check In on a scheduled match. The
Station fields must be selects listing the seeded stations, with any in-use one
labelled "in use (match #N)". Pick the same station for both players and submit —
expect an amber toast naming the collision and **no** state change on the row.
Then pick two distinct free stations and confirm both the assignment and the
"Match #N checked in." toast.

Repeat against the `second` tenant (`/t/second/...`), which has no pool: the
fields must fall back to text inputs and free text must still save.

### Done when

A station cannot be double-booked within a match or across two matches in play; a
community with no pool is unaffected; the leak test passes; the picker renders at
both widths.

---

## T2.4 — Promote the station out of the italic parenthetical

**Depends on:** T2.3 (so there is something worth promoting).

**Why.** The station is what the proctor physically directs people to, and it
renders as the least prominent thing in the cell: grey italic `(12)`.

### Files

- `theme/tables/match_slots.py`
- `theme/tables/match_grid.py`

### Change

`theme/tables/match_slots.py`, `PLAYERS_SLOT` (~line 275). Replace:

```html
                        <span v-if="__IA__ && player.station" class="st-neutral italic-note"> ({{ player.station }})</span>
```

with:

```html
                        <span v-if="__IA__ && player.station" class="wiz-chip wiz-chip--neutral q-ml-xs">
                            <q-icon name="chair" size="12px" />{{ player.station }}</span>
```

`theme/tables/match_grid.py`, `_PLAYERS` (~line 68) — the same replacement on the
mobile card's equivalent span.

`.wiz-chip` and `.wiz-chip--neutral` already exist in `static/css/styles.css`
(~line 288) with light/dark parity, so no CSS change is needed. Do not add inline
colours.

### Verify

Screenshot a checked-in row with stations assigned at 1500px and 430px. The
station must read as a chip beside the player name in both, in light and dark
theme (toggle with the theme control in the header).

---

## Wave 2 wrap-up

```bash
poetry run pytest
```

Browser-verify `/volunteer/proctor-station` and `/admin/schedule` at both widths,
plus `/` and `/home/player` (they embed the same players slot and must not have
regressed). Also load the `second` tenant to prove the no-pool fallback.

Two PRs: *"Say check-in when checking in, and let proctors fix a station"*
(T2.1, T2.2, T2.4) and *"Add a venue station pool and reject double-booked
stations"* (T2.3).
