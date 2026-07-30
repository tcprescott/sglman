# Wave 3 — the volunteer's side is a page, not a receipt

**Read [README.md](README.md) first**, including open questions Q2 (release vs.
request) and Q4 (does a time change clear acknowledgments) — they decide T3.1 and
T3.4. **Waves 1 and 2 must be merged**: every DM this wave adds is conditional on
the wave 1 invariant that a draft has never been announced, so a draft's removal
stays silent while a published assignment's does not.

Three findings and two root causes, all on the same surface.
[F3](../../reviews/volunteer-hub-ux.md#f3--critical--a-volunteer-cannot-decline-hand-back-or-swap-a-shift) —
`my_shifts.py` renders exactly one control, **Acknowledge**; `unassign` is
coordinator-only, so the only exit is finding a coordinator out of band, which
means the grid is more confident than the truth.
[F4](../../reviews/volunteer-hub-ux.md#f4--major--the-shift-never-says-what-the-shift-is) —
`VolunteerPosition.description` and `VolunteerShift.notes` are both editable and
rendered nowhere ([RC3](../../reviews/volunteer-hub-ux.md#rc3--the-coordinators-page-is-a-builder-the-volunteers-is-a-receipt)).
[F5](../../reviews/volunteer-hub-ux.md#f5--major--removing-a-volunteer-from-a-shift-tells-them-nothing) /
[RC2](../../reviews/volunteer-hub-ux.md#rc2--notification-is-one-directional-the-same-shape-as-crew) —
assignment DMs; un-assignment, a cleared draft and a moved shift notify nobody.

| Task | Fixes | Depends on | Size |
|---|---|---|---|
| T3.1 | F3 (the service half), RC2 | — | **large** — new verb + coordinator fan-out |
| T3.2 | F3 (the page half) | T3.1 | medium |
| T3.3 | F4, RC3 | — | medium |
| T3.4 | F5, RC2 | — | medium |
| T3.5 | — (seed + docs) | T3.1, T3.4 | small |

T3.1 + T3.2 are one PR (the verb and its button). T3.3 is independent and can go
in parallel. T3.4 + T3.5 are a third.

---

## T3.1 — `release`: a volunteer can hand a shift back

**Why.** F3. A commentator can withdraw from a crew slot in two clicks
([`crew_service.undo_crew_signup`](../../../application/services/crew_service.py#L96));
the same person, doing the same kind of favour through a different door, cannot.

**Shape.** Mirror `undo_crew_signup`: the row is deleted, the actor is the
volunteer themselves, and the audit records the reason. Unlike crew, the
coordinators are DMed — F3 and F5 are the same silence in two directions, and a
released shift is the one that needs cover.

### Files

- `application/services/volunteer/volunteer_schedule_service.py`
- `application/services/audit_service.py`
- `application/events/event_types.py`
- `application/utils/discord_messages.py`
- `api/routers/volunteers.py`, `api/schemas/volunteers.py`

### Change 1 — the service method

Beside `acknowledge`
([`:284`](../../../application/services/volunteer/volunteer_schedule_service.py#L284)),
sharing its ownership check:

```python
    async def release(
        self, assignment_id: int, user: User, reason: Optional[str] = None,
    ) -> None:
        """Give a shift back. The volunteer's own decision, not the coordinator's.

        Frees the slot immediately and DMs the coordinators — a schedule showing
        someone who has already said no is worse than an open one.
        """
        assignment = require_found(
            await self.assignment_repository.get_by_id(assignment_id), "Volunteer assignment"
        )
        if assignment.user_id != user.id:
            raise ValueError("You can only release your own assignments.")
        shift = assignment.shift
        if assignment.checked_in_at is not None:
            raise ValueError(
                "You are already checked in for this shift — talk to your coordinator."
            )
        if shift.ends_at <= datetime.now(timezone.utc):
            raise ValueError("That shift has already finished.")
        details = {
            'assignment_id': assignment.id, 'shift_id': shift.id, 'user_id': user.id,
            'reason': (reason or '').strip() or None,
            'hours_notice': round(
                (shift.starts_at - datetime.now(timezone.utc)).total_seconds() / 3600.0, 1),
        }
        await self.assignment_repository.delete(assignment)
        await self.audit_service.write_and_publish(
            user, AuditActions.VOLUNTEER_RELEASED, details, EventType.VOLUNTEER_RELEASED,
        )
        await self._notify_coordinators_of_release(user, shift, details)
```

`hours_notice` is the number the coordinator's DM and any future report both need,
and it is only computable at this moment — record it rather than deriving it later
from the audit timestamp.

A draft cannot reach this method (wave 1 hides it), but do not add a guard: if one
somehow does, releasing it is harmless and the audit row is still correct.

### Change 2 — the coordinator fan-out

```python
    async def _notify_coordinators_of_release(
        self, volunteer: User, shift: VolunteerShift, details: Dict,
    ) -> None:
        """Best-effort DM to whoever has to find cover. Never raises."""
        from application.repositories import UserRoleRepository
        from application.services.tenant_service import TenantService
        from application.utils.discord_embeds import volunteer_embed
        from application.utils.discord_messages import volunteer_released_dm
        from models import Role

        recipients = {}
        for role in (Role.VOLUNTEER_COORDINATOR, Role.STAFF):
            for candidate in await UserRoleRepository.list_users_with_role(role):
                recipients[candidate.id] = candidate
        ...
```

`list_users_with_role` is already tenant-scoped
([`user_role_repository.py:60-65`](../../../application/repositories/user_role_repository.py)).
Dedupe by id (a coordinator who is also staff gets one DM), skip anyone without a
`discord_id` or with `dm_notifications` off, and enqueue through
`discord_queue.enqueue(...)` exactly like
[`request_acknowledgment`](../../../application/services/volunteer/volunteer_schedule_service.py#L360).
This is the first place in the codebase that DMs a *role*, so keep the helper
private to this service — do not build a general broadcast utility for one caller.

### Change 3 — the message

`application/utils/discord_messages.py`, beside the other volunteer builders
([`:372-409`](../../../application/utils/discord_messages.py)), reusing
`_volunteer_shift_lines`:

```python
def volunteer_released_dm(
    volunteer_name: str,
    position_name: str,
    label: Optional[str],
    starts_display: str,
    ends_display: str,
    hours_notice: Optional[float] = None,
    reason: Optional[str] = None,
) -> str:
    """DM to the coordinators when a volunteer gives a shift back."""
```

Copy: `**{volunteer_name}** has given back a volunteer shift.`, the shift block,
then `Notice: about {hours_notice} hour(s).` and `Their reason: "{reason}"` when
present, and `This slot is open again.` last. Embed via `volunteer_embed(title='🙋
Volunteer dropped a shift', …)` — the existing builder already renders
Position/Start/End.

### Change 4 — the audit action and the event

`audit_service.py`: `VOLUNTEER_RELEASED = 'volunteer.released'`.

`application/events/event_types.py`: add `VOLUNTEER_RELEASED = 'volunteer.released'`
to the Volunteer block ([`:45-48`](../../../application/events/event_types.py)) **and
to `EventType.ALL`** ([`:132`](../../../application/events/event_types.py)). This is
a new member of an external contract, which is allowed; a rename would not be.

It is deliberately **not** `VOLUNTEER_UNASSIGNED`: a subscriber has to be able to
tell "the coordinator removed them" from "the volunteer dropped out", because only
the second one needs cover found. Say that in a comment next to the member.

### Change 5 — REST

`DELETE /volunteers/me/assignments/{assignment_id}` with an optional
`reason` body field, `require_write_actor`, calling `release(assignment_id, actor,
reason)`. It sits with the other `/me/*` endpoints
([`:185-220`](../../../api/routers/volunteers.py)) — self-service, not the
coordinator's `DELETE /volunteers/assignments/{id}`. 204 on success; the service's
`ValueError`s become 400 through `ServiceErrorRoute`.

### Tests

`tests/services/test_volunteer_schedule_service.py`: refuses someone else's
assignment, refuses when `checked_in_at` is set, refuses a finished shift, deletes
+ audits + publishes on the happy path, and records `reason=None` for whitespace.

`tests/services/test_volunteer_scheduling.py` (DB-backed): after `release` the slot
shows open in `coverage()`.

`tests/api/test_volunteers.py`: 204 on your own, 400 on someone else's.

A DM assertion belongs with the others in
`tests/services/test_volunteer_schedule_service.py` — patch `discord_queue.enqueue`
and assert one call per coordinator, none for a coordinator with
`dm_notifications=False`, and none at all when nobody holds either role.

### Verify

Two contexts. As `player_one` release a published shift with a reason; as
`staff_user` confirm the grid shows the slot open again, and confirm the DM in
`/tmp/app.log` names the volunteer, the shift and the notice hours.

---

## T3.2 — "Can't make this" on My Shifts

**Depends on T3.1.**

### Files

- `pages/volunteer_tabs/my_shifts.py`

### Change

Beside Acknowledge in the card's action row
([`:49-62`](../../../pages/volunteer_tabs/my_shifts.py)) — shown whether or not
the shift is acknowledged, since acknowledging is not a commitment you cannot
revise:

```python
                            ui.button("Can't make this", icon='event_busy',
                                      on_click=lambda a=assignment: confirm_release(a)) \
                                .props('flat color=negative')
```

`confirm_release` opens a `ui.dialog` (not the plain `ConfirmationDialog` — this
one collects text) with:

- the shift's position, label and Eastern start→end, so the volunteer is releasing
  the shift they think they are
- `ui.textarea('Reason (optional)')`, hinted `Your coordinator sees this.`
- a warning line when the shift starts within the tenant's reminder lead
  (`SystemConfigService.get_volunteer_reminder_lead_minutes`) or within 24 hours,
  whichever is longer: `This shift starts in about 3 hours. Your coordinator will
  be told right away, but may not find cover.`
- buttons `Keep it` / `Give it back` (negative)

On success `ui.notify('Shift released. Your coordinator has been told.',
color='info')` and `shift_list.refresh()`; on `ValueError` / `PermissionError`,
`notify_error(e)`.

The card's layout is a `ui.row` of badges and one button today; two buttons plus a
badge stack needs a re-check at 390px — put the actions in their own wrapped row
rather than widening the header row.

### Tests

Presentation; verify in the browser. The lead-window copy decision is worth one
unit test if you extract it — a module-level
`release_warning(starts_at, lead_minutes) -> str | None` in `my_shifts.py` is
testable without a slot context, and then `tests/theme/` can assert it is silent at
72 hours and speaks at 3.

### Verify

As `player_one` at 1500px and 390px: release a shift far out (no warning line) and
one inside the lead (warning line present), and confirm the second still succeeds.

---

## T3.3 — The shift brief: say what the shift is

**Why.** F4. The measured card is position name, optional label, start→end, badges,
Acknowledge — and for a first-time volunteer that card is the entire brief. The two
text fields that would answer "where do I go, who do I report to, what do I bring"
are captured by the coordinator's dialogs
([`volunteer_shift_dialog.py:88`](../../../theme/dialog/volunteer_shift_dialog.py),
[`volunteer_position_dialog.py:35`](../../../theme/dialog/volunteer_position_dialog.py))
and rendered nowhere. The roster page already proves the data is presentable.

### Files

- `application/repositories/volunteer_assignment_repository.py`
- `pages/volunteer_tabs/my_shifts.py`
- `pages/admin_tabs/admin_volunteers.py`

### Change 1 — the volunteer's card carries the brief

Under the provenance caption wave 1 added:

- `shift.position.description`, when set, as `text-body2` — this is the standing
  description of the job
- `shift.notes`, when set, in a bordered `q-pa-sm` block labelled **For this
  shift** — the per-shift instruction, which must not be visually merged with the
  standing one
- **Who else is on** — `With: Alice, Bob` from the shift's other assignments, or
  `You are the only one scheduled for this slot.` when there are none. Skip drafts
  in that list: naming someone who has not been told is the wave 1 invariant
  leaking out sideways.

The last one needs the shift's sibling assignments. Add a dedicated repository
method rather than widening `_PREFETCH` for every caller:

```python
    _PREFETCH_WITH_SHIFTMATES = _PREFETCH + ('shift__assignments', 'shift__assignments__user')
```

used by `list_for_user(..., with_shiftmates=True)`, which My Shifts passes and the
REST endpoint does not.

### Change 2 — the coordinator can see what they wrote

`_render_shift_card` ([`:130-153`](../../../pages/admin_tabs/admin_volunteers.py)):
when `shift.notes` is set, a `ui.icon('sticky_note_2')` beside the `filled/needed`
badge whose tooltip is the notes text, so a write-only field becomes checkable
from the grid. Position descriptions belong in the position header row
([`:114`](../../../pages/admin_tabs/admin_volunteers.py)) as a `text-caption` line
under the name.

### Tests

`tests/services/test_volunteer_scheduling.py`: `assignments_for_user(...,
with_shiftmates=True)` returns the sibling assignments and the plain call does not
(so nobody quietly makes the expensive version the default).

### Verify

Give a seeded shift notes and its position a description (T3.5 seeds this), then
read the volunteer's card at 390px: three text blocks and a name list must not turn
the card into a wall — check the measured height against the audit's "fits".

---

## T3.4 — Stop the silent reverse transitions

**Why.** F5/RC2. `unassign` audits and publishes and sends nothing, so a
volunteer's shift disappears from My Shifts on their next visit. Editing a shift's
time notifies nobody, so a volunteer can turn up four hours late for work they
acknowledged. Combined with F3 before T3.1, a volunteer's schedule could change in
both directions without a single message either way.

### Files

- `application/services/volunteer/volunteer_schedule_service.py`
- `application/utils/discord_messages.py`

### Change 1 — removal tells the volunteer

In `unassign` ([`:270-282`](../../../application/services/volunteer/volunteer_schedule_service.py#L270)),
after the audit and event:

```python
        if not assignment.auto_generated:
            await self._notify_removed(assignment.user, assignment.shift)
```

The guard is the whole point: an unpublished draft's removal is silent because its
creation was. `volunteer_unassigned_dm` reads *"You have been taken off a volunteer
shift."* + the shift block + *"No action needed. Ask your coordinator if this looks
wrong."* — with no acknowledge button, so use `send_dm` rather than
`send_dm_with_volunteer_acknowledgment_button`.

`clear_draft` stays silent and gains a one-line comment saying why, so the next
reader does not "fix" it.

### Change 2 — a moved shift re-asks

`update_shift` ([`:167-182`](../../../application/services/volunteer/volunteer_schedule_service.py#L167))
currently validates, saves and audits. Capture the old times first, and when
`starts_at` or `ends_at` actually changed:

- clear `acknowledged_at` on every non-draft assignment of that shift (Q4) and say
  so in the audit details (`{'reacknowledge_cleared': n}`)
- DM each of those volunteers with `volunteer_shift_changed_dm(old_starts_display,
  old_ends_display, …)` — *"A shift you are on has moved."*, both windows, and
  *"Tap Acknowledge to confirm you can still cover it."* — through the
  acknowledgment-button path, so the reply lands back in the same flow

A slots-only or label-only edit notifies nobody. Do not clear check-ins.

### Tests

`tests/services/test_volunteer_schedule_service.py`:

- `unassign` DMs a published assignment's volunteer and does **not** DM a draft's
- `update_shift` with a new start clears acknowledgments and enqueues one DM per
  assignee; with only `slots_needed` changed it does neither
- a volunteer with `dm_notifications=False` gets no DM in either path

### Verify

Two contexts, both directions: as `staff_user` remove `player_one` from a
published shift and confirm the DM; move another shift by four hours and confirm
`player_one`'s card loses its **Acknowledged** badge and their DM asks again.

---

## T3.5 — Seed the brief, and write the notification matrix down

**Depends on T3.1, T3.4.**

### Files

- `scripts/seed_volunteers.py`
- `docs/reference/services.md`
- `docs/features/discord.md`

### Change 1 — dev data with something to read

In `seed_volunteers.py`: give two positions a `description` in the
`get_or_create` defaults (`"Check-in Desk"` → *"Greet arrivals at the main door,
check them against the entrant list, hand out badges."*), and give the `Shift 1`
rows of one position `notes` (*"Report to the info desk 10 minutes early. Radio
channel 2. Bring a jacket — the door is draughty."*). Keep both idempotent: only
set them when the existing row's field is empty, the way the volunteer notes at
[`:80-84`](../../../scripts/seed_volunteers.py) already do.

### Change 2 — the matrix

`docs/reference/services.md`'s volunteer section gains a table, because "who gets
told what" is now the subsystem's most load-bearing rule and it is currently
spread across five methods:

| Transition | Volunteer | Coordinators |
|---|---|---|
| Manual assign | DM + Acknowledge | — |
| Draft created | — | — (grid + banner) |
| Draft published | DM + Acknowledge | — |
| Draft cleared | — | — |
| Shift time changed | DM + Acknowledge (ack cleared) | — |
| Coordinator un-assigns | DM (no button) | — |
| Volunteer releases | — | DM |
| Reminder lead reached | DM + Acknowledge | — |

Add the two new DM builders to whatever list `docs/features/discord.md` keeps of
outbound messages.

### Verify

Re-seed and read one volunteer card and one coordinator card end to end. Then
`scripts/ui_flag_sweep.sh` — this wave adds no new page, but it touches two, and
the sweep is cheap.
