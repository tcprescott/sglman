# Wave 1 — draft means draft

**Read [README.md](README.md) first**, including the five open questions — Q1
(hide vs. label) decides T1.1's shape and must be answered before you start.

This wave fixes the audit's blocker, [F1](../../reviews/volunteer-hub-ux.md#f1--blocker--a-draft-shift-is-a-real-commitment-to-everyone-except-the-coordinator)
and its root cause [RC1](../../reviews/volunteer-hub-ux.md#rc1--the-draft-has-no-publish-step-so-auto_generated-is-honoured-by-exactly-one-widget):
`generate_draft` writes assignments the volunteer sees as ordinary shifts, can
acknowledge, and loses without a word. Nothing converts a draft into a
commitment, so `auto_generated` is honoured by exactly one chip in one widget.

After this wave one sentence is true everywhere: **`auto_generated=True` means
nobody has been told.** T1.1 makes every consumer honour it, T1.2 adds the verb
that ends it, T1.3 puts that verb on the screen.

| Task | Fixes | Depends on | Size |
|---|---|---|---|
| T1.1 | F1 bullets 1 & 3, RC1 | — | small |
| T1.2 | F1 (the missing verb), RC1 | T1.1 | **large** — new service method + notifications |
| T1.3 | F1 bullet 1 | T1.2 | medium |
| T1.4 | F1 bullet 2 | T1.1 | small |
| T1.5 | — (seed + docs) | T1.2 | small |

T1.1 and T1.2 ship in one PR — the invariant and the escape hatch belong
together, and T1.1 alone would leave drafts with no way to become real. T1.3–T1.5
can follow in a second PR.

---

## T1.1 — Make every consumer honour `auto_generated`

**Why.** Measured: an auto-fill created 16 draft assignments, 4 of them
`player_one`'s, and their page showed four unmarked shifts with an Acknowledge
button. Three consumers ignore the flag today —
[`list_for_user`](../../../application/repositories/volunteer_assignment_repository.py#L66)
(feeds My Shifts and `GET /volunteers/me/assignments`),
[`due_for_reminder`](../../../application/repositories/volunteer_assignment_repository.py#L96)
(the reminder worker, so a draft's debut in a volunteer's DMs is "your shift
starts soon") and
[`acknowledge`](../../../application/services/volunteer/volunteer_schedule_service.py#L284)
(which accepts a confirmation that `delete_auto_for_window` then deletes).

### Files

- `application/repositories/volunteer_assignment_repository.py`
- `application/services/volunteer/volunteer_schedule_service.py`

### Change 1 — drafts are not the volunteer's shifts

`list_for_user`. Add a keyword-only opt-in rather than changing the signature's
meaning silently, and default it off:

```python
    @staticmethod
    async def list_for_user(
        user: User,
        upcoming_after: Optional[datetime] = None,
        *,
        include_drafts: bool = False,
    ) -> List[VolunteerAssignment]:
        """This user's assignments. Drafts are excluded by default: an
        ``auto_generated`` row is the coordinator's sketch and the volunteer has
        not been told about it (see ``publish_draft``)."""
        query = scoped(VolunteerAssignment.filter(user=user))
        if not include_drafts:
            query = query.filter(auto_generated=False)
        if upcoming_after is not None:
            query = query.filter(shift__ends_at__gte=upcoming_after)
        return await query.order_by('shift__starts_at').prefetch_related(*_PREFETCH)
```

Thread the same keyword through
`VolunteerScheduleService.assignments_for_user` ([`:320`](../../../application/services/volunteer/volunteer_schedule_service.py#L320)).
Its two callers — [`my_shifts.py:30`](../../../pages/volunteer_tabs/my_shifts.py)
and [`api/routers/volunteers.py:220`](../../../api/routers/volunteers.py) — both
want the default, so neither changes. Do not add a query parameter to the REST
endpoint: no client has a reason to ask for someone's unannounced drafts.

### Change 2 — a draft is never the first DM a volunteer gets

`due_for_reminder`. One filter, and keep the "deliberately cross-tenant" comment
exactly as it is:

```python
            VolunteerAssignment.filter(
                auto_generated=False,
                reminder_sent_at__isnull=True,
                shift__starts_at__gte=window_start,
                shift__starts_at__lte=window_end,
            )
```

Add to the docstring: *"Drafts are skipped — the reminder must not be the message
that first tells someone they have a shift."*

### Change 3 — a draft cannot be acknowledged

`acknowledge`, after the ownership check and before the idempotency check:

```python
        if assignment.auto_generated:
            raise ValueError(
                "That shift is still a draft — your coordinator has not confirmed it yet."
            )
```

This is the defence-in-depth half of the change: the button is gone from the page
in T1.3's world, but the same service method is reachable from
`POST /volunteers/assignments/{id}/acknowledge`
([`api/routers/volunteers.py:158`](../../../api/routers/volunteers.py)) and from
the Discord button
([`discordbot/volunteer_acknowledgment.py:49`](../../../discordbot/volunteer_acknowledgment.py)),
and a stale DM from before this wave can still be clicked. `ValueError` gives the
REST caller a 400 and the Discord handler its ephemeral reply for free.

### Tests

`tests/services/test_volunteer_schedule_service.py` (the mocked-repository unit
file):

```python
async def test_acknowledge_refuses_a_draft(service):
    service.assignment_repository.get_by_id = AsyncMock(
        return_value=make_assignment(auto_generated=True))
    with pytest.raises(ValueError, match='still a draft'):
        await service.acknowledge(1, SimpleNamespace(id=42))
```

`make_assignment` needs `auto_generated=False` added to its defaults
([`:33-37`](../../../tests/services/test_volunteer_schedule_service.py)).

`tests/services/test_volunteer_scheduling.py` (the DB-backed file) — the two
repository filters, which the mocked file cannot prove:

- a draft assignment is absent from `assignments_for_user`, present with
  `include_drafts=True`
- a draft assignment is absent from `due_for_reminder` while an otherwise
  identical published one is returned

`tests/api/test_volunteers.py`: `GET /volunteers/me/assignments` omits a draft;
`POST /volunteers/assignments/{draft_id}/acknowledge` returns 400.

### Verify

Two contexts. As `staff_user` auto-fill a future day; as `player_one` reload
`/t/default/volunteer/my-shifts` and confirm it still reads *"You have no
upcoming shifts."* Then check the log has no reminder DM for the drafted shifts
(`grep -i 'DM to' /tmp/app.log`).

---

## T1.2 — `publish_draft`: the verb that was missing

**Depends on T1.1.**

**Why.** RC1: `clear_draft` is the only other verb and it deletes. There is no
publish method, no bulk notify, no flag flip — so the coordinator's review has no
completion, and the only way to commit a drafted schedule is to remove each
assignment and re-add it by hand (2 interactions × 16).

**Shape.** Per-assignment confirmation lives on `VolunteerScheduleService` (it
owns assignments, notification and the acknowledgment DM); the window-level loop
lives on `VolunteerAutoscheduleService` next to `generate_draft` and `clear_draft`
(it owns the draft as a unit). Publishing a draft assignment produces exactly what
a manual assign produces — a DM with an Acknowledge button, a
`VOLUNTEER_ASSIGNED` event and an audit row — because from the volunteer's side it
*is* the same event, just decided in bulk.

### Files

- `application/repositories/volunteer_assignment_repository.py`
- `application/services/volunteer/volunteer_schedule_service.py`
- `application/services/volunteer/volunteer_autoschedule_service.py`
- `application/services/audit_service.py`
- `tests/services/test_event_audit_parity.py`

### Change 1 — the repository can list and flip drafts

Two methods beside `delete_auto_for_window`
([`:80`](../../../application/repositories/volunteer_assignment_repository.py#L80)),
reusing its resolve-shift-ids-then-filter shape so they keep working on SQLite:

```python
    @staticmethod
    async def list_auto_for_window(start: datetime, end: datetime) -> List[VolunteerAssignment]:
        """Draft assignments whose shift overlaps the window, prefetched for notification."""
        shift_ids = await scoped(VolunteerShift.filter(
            starts_at__lt=end, ends_at__gt=start,
        )).values_list('id', flat=True)
        if not shift_ids:
            return []
        return await (
            scoped(VolunteerAssignment.filter(
                auto_generated=True, shift_id__in=list(shift_ids),
            ))
            .order_by('shift__starts_at')
            .prefetch_related(*_PREFETCH)
        )

    @staticmethod
    async def mark_published(assignment: VolunteerAssignment) -> VolunteerAssignment:
        assignment.auto_generated = False
        await assignment.save(update_fields=['auto_generated', 'updated_at'])
        return assignment
```

### Change 2 — `confirm_assignment` on the schedule service

Beside `assign`. It is the single place where "this volunteer has now been told"
becomes true:

```python
    async def confirm_assignment(
        self, actor: User, assignment: VolunteerAssignment, *, notify: bool = True,
    ) -> VolunteerAssignment:
        """Turn one draft assignment into a commitment: flip the flag, DM the
        volunteer, emit the same event a manual assign emits. Idempotent."""
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can publish assignments.",
        )
        if not assignment.auto_generated:
            return assignment
        await self.assignment_repository.mark_published(assignment)
        await self.audit_service.write_and_publish(
            actor, AuditActions.VOLUNTEER_ASSIGNED,
            {'assignment_id': assignment.id, 'shift_id': assignment.shift_id,
             'user_id': assignment.user_id, 'published_from_draft': True},
            EventType.VOLUNTEER_ASSIGNED,
        )
        if notify:
            await self.request_acknowledgment(
                assignment, assignment.shift, assignment.user,
            )
        return assignment
```

Rename `_request_acknowledgment` → `request_acknowledgment`
([`:360`](../../../application/services/volunteer/volunteer_schedule_service.py#L360))
and update its one existing caller in `assign`. It stays a best-effort,
never-raising DM.

Note the audit detail `published_from_draft: True` — the audit log is how a
coordinator later answers "when was this person actually told?", and the
`volunteer.assigned` row's timestamp is now that moment rather than the draft's.

### Change 3 — `publish_draft` on the autoschedule service

```python
    async def publish_draft(self, actor: User, start: datetime, end: datetime) -> Dict:
        """Commit every draft assignment in the window and tell each volunteer.

        The inverse of ``clear_draft``: same window, same authorization, opposite
        decision. Returns counts for the coordinator's confirmation toast.
        """
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can publish drafts.",
        )
        drafts = await self.assignment_repository.list_auto_for_window(start, end)
        for assignment in drafts:
            await self.schedule_service.confirm_assignment(actor, assignment)
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_DRAFT_PUBLISHED,
            {'published': len(drafts), 'start': start, 'end': end},
        )
        return {'published': len(drafts),
                'volunteers': len({a.user_id for a in drafts})}
```

Not in a transaction, deliberately: each `confirm_assignment` enqueues a DM, and a
rollback cannot un-send one. Publishing 16 rows one at a time and failing on the
tenth leaves ten people correctly told, which is recoverable; the eleventh
publishes on the next click because `confirm_assignment` is idempotent.

### Change 4 — the new audit action and its ledger entry

`application/services/audit_service.py`, in the `volunteer.*` block
([`:181-199`](../../../application/services/audit_service.py)):

```python
    VOLUNTEER_DRAFT_PUBLISHED = 'volunteer.draft_published'
```

It gets **no** mirror `EventType`: the domain change subscribers care about is
per-volunteer, and `confirm_assignment` already emits `VOLUNTEER_ASSIGNED` for
each one. Add it to `_EVENT_CANDIDATES` in
`tests/services/test_event_audit_parity.py`, beside the existing
`VOLUNTEER_DRAFT_GENERATED` / `VOLUNTEER_DRAFT_CLEARED` entries
([`:194-195`](../../../tests/services/test_event_audit_parity.py)), with the
reasoning as a comment:

```python
    # The coordinator's bulk decision; the per-volunteer commitments it makes are
    # each emitted as VOLUNTEER_ASSIGNED by confirm_assignment.
    AuditActions.VOLUNTEER_DRAFT_PUBLISHED,
```

### Tests

`tests/services/test_volunteer_autoschedule_service.py`:

- `publish_draft` flips every draft in the window and returns
  `{'published': 3, 'volunteers': 2}`
- publishing twice publishes 0 the second time (idempotent through
  `confirm_assignment`)
- a published assignment **survives `clear_draft`** — the regression that F1's
  second bullet describes
- `publish_draft` for a window with no drafts audits `published: 0` and sends
  nothing

`tests/services/test_volunteer_schedule_service.py`: `confirm_assignment` calls
`request_acknowledgment` once, writes `VOLUNTEER_ASSIGNED` with
`published_from_draft: True`, and returns early without notifying when the
assignment is already published.

### Verify

Two contexts, the audit's own experiment run forwards. As `staff_user`: auto-fill
a future day, confirm the chips are outlined drafts, click **Publish draft**. As
`player_one`: reload My Shifts — the shifts are now there with Acknowledge.
Acknowledge one, then as `staff_user` click **Clear draft** and confirm the
acknowledged shift is still on the volunteer's page. In the DM log, one
`volunteer_ack` DM per published assignment and none before publish.

---

## T1.3 — Put publish on the screen, and say what a draft is

**Depends on T1.2.**

**Why.** The coordinator's page currently offers *Auto-fill* and *Clear draft* —
create and destroy, with no commit. And the only marker that 16 assignments are
provisional is a chip outline whose tooltip reads "Auto-generated draft", which
says how the row was made rather than what is true of it.

### Files

- `pages/admin_tabs/admin_volunteers.py`

### Change 1 — a draft banner that carries the two decisions

The controls card ([`:71-92`](../../../pages/admin_tabs/admin_volunteers.py))
keeps *Auto-fill*, *Manage positions*, *Export data* and *Reset*. Move **Clear
draft** out of it and into a new `@ui.refreshable` banner between the controls and
the grid, which renders only when the selected day has drafts:

```python
        @ui.refreshable
        async def draft_banner() -> None:
            win_start, win_end = _day_window(state['day'])
            pending = await schedule_service.count_drafts(win_start, win_end)
            if not pending:
                return
            with ui.card().classes('full-width q-pa-sm wiz-draft-banner'):
                with ui.row().classes('items-center gap-2 full-width'):
                    ui.icon('edit_note', color='secondary')
                    ui.label(
                        f'{pending} draft assignment(s) on this day. '
                        'The volunteers have not been told yet.'
                    ).classes('text-body2')
                    ui.space()
                    ui.button('Publish draft', icon='send',
                              on_click=lambda: confirm_publish(pending)) \
                        .props('color=positive')
                    ui.button('Clear draft', icon='clear_all',
                              on_click=lambda: clear_draft()).props('flat color=negative')
```

`count_drafts(start, end)` is a one-line addition to `VolunteerScheduleService`
over a `VolunteerAssignmentRepository.count_auto_for_window` — the page must not
count rows itself.

Every existing `grid.refresh()` in the page gains a `draft_banner.refresh()`
alongside it (`auto_fill`, `clear_draft`, the publish handler, the chip's
`remove`, `open_assign_dialog`'s `do_assign`, `generate_shifts`, the reset
dialog). There are eight; missing one leaves a banner claiming drafts that are
gone.

### Change 2 — publish asks first, because it sends DMs

```python
        async def confirm_publish(pending: int) -> None:
            async def on_confirm() -> None:
                confirm.dialog.close()
                try:
                    result = await autoschedule_service.publish_draft(*_day_window(state['day']))
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify(
                    f"Published {result['published']} assignment(s) to "
                    f"{result['volunteers']} volunteer(s). Each got a Discord DM.",
                    color='positive',
                )
                grid.refresh()
                draft_banner.refresh()

            confirm = ConfirmationDialog(
                message=(f'Publish {pending} draft assignment(s)? Each volunteer gets a '
                         'Discord DM asking them to acknowledge. This cannot be undone — '
                         'removing an assignment afterwards notifies them again.'),
                on_confirm=on_confirm, confirm_text='Publish & notify',
            )
            confirm.open()
```

(The real call passes `actor` first — `publish_draft(actor, win_start, win_end)`.)

Confirmation is warranted here and nowhere else new in this wave: it is the one
action that reaches people outside the room. Do not add one to *Clear draft* — with
T1.1 in place, clearing a draft is invisible to everyone but the coordinator.

### Change 3 — the chip says what is true, not how it happened

[`_render_assignment_chip`](../../../pages/admin_tabs/admin_volunteers.py#L155):

```python
                if assignment.auto_generated:
                    chip.props('outline color=secondary') \
                        .tooltip('Draft — this volunteer has not been told')
```

### Tests

Presentation copy is not unit-tested in this repo; verify in the browser. Do add
`tests/services/test_volunteer_scheduling.py` coverage for `count_drafts` (drafts
in the window counted, published ones and drafts outside the window not).

### Verify

`/t/default/admin/volunteers` at 1500px and 390px, before and after an auto-fill:
the banner appears with the count, publish asks first, and after publishing the
banner is gone and every chip is solid. Screenshot both widths — the banner's
button row is the kind of thing that wraps badly on a phone.

---

## T1.4 — Say where a shift came from

**Depends on T1.1.**

**Why.** F1's first bullet, from the other side: even with drafts hidden, the
volunteer's card is four facts with no provenance — nothing says who scheduled
them or when, so "I never agreed to this" has no answer on the page. One caption
line closes it, and it is the natural home for the acknowledgment timestamp that
is currently only a badge.

### Files

- `pages/volunteer_tabs/my_shifts.py`

### Change

In the card ([`:40-62`](../../../pages/volunteer_tabs/my_shifts.py)), under the
existing start→end caption:

```python
                            assigned_by = assignment.assigned_by
                            provenance = 'Scheduled'
                            if assigned_by is not None:
                                provenance = f'Scheduled by {assigned_by.preferred_name}'
                            provenance += f' · {format_eastern_display(assignment.created_at)}'
                            if assignment.acknowledged_at:
                                provenance += (
                                    f' · you acknowledged '
                                    f'{format_eastern_display(assignment.acknowledged_at)}'
                                )
                            ui.label(provenance).classes('text-caption text-grey')
```

`assigned_by` is not in the repository's `_PREFETCH`
([`:14`](../../../application/repositories/volunteer_assignment_repository.py)) —
add `'assigned_by'` to it. It is one extra join on a list that is already
prefetching three relations, and the coordinator's grid benefits too.

While in this file, replace the hand-rolled `ui.notify(str(e), color='warning')`
at `:59-60` with `notify_error(e)` per the README's error convention.

### Tests

None (presentation). The prefetch change is covered by the existing My Shifts
tests continuing to pass; add an assertion in
`tests/services/test_volunteer_scheduling.py` that `assignments_for_user` returns
rows whose `assigned_by` is populated without a further await.

### Verify

As `player_one` on `/t/default/volunteer/my-shifts` after T1.2's publish: the
caption reads *"Scheduled by Staff User · …"*, and after acknowledging, the same
line carries the acknowledgment time. 390px too — this line wraps to two.

---

## T1.5 — Seed a draft, and write the invariant down

**Depends on T1.2.**

**Why.** `scripts/seed_volunteers.py` creates exactly one assignment
([`:152-158`](../../../scripts/seed_volunteers.py)) and it is a published one, so a
dev environment cannot show the draft state at all — which is why the audit had to
generate one by hand before it could see the bug. And the reference docs describe
My Shifts as "position/label, start→end, and either an Acknowledged badge or an
Acknowledge button", which after this wave is no longer the whole story.

### Files

- `scripts/seed_volunteers.py`
- `docs/reference/services.md`
- `docs/reference/frontend.md`

### Change 1 — one drafted shift in the dev data

Beside the existing published assignment, on day 2 so the two states sit on
different days and the grid shows each cleanly:

```python
    second_day = event_days[1].isoformat()
    draft_shift = shift_index.get((second_day, "Check-in Desk|Shift 1"))
    if draft_shift:
        # An unpublished autoscheduler draft: outlined on the coordinator's grid,
        # invisible on the volunteer's page until Publish draft.
        await VolunteerAssignment.get_or_create(
            shift=draft_shift, user=users["player_three"], tenant=tenant,
            defaults={"assigned_by": staff, "auto_generated": True},
        )
```

### Change 2 — the docs

`docs/reference/services.md`, the `VolunteerScheduleService` and
`VolunteerAutoscheduleService` method tables (from
[`:978`](../../../docs/reference/services.md)): add `confirm_assignment`,
`count_drafts` and `publish_draft` rows, and add a short paragraph to the
volunteer-subsystem intro at
[`:937`](../../../docs/reference/services.md) stating the invariant:

> A draft assignment (`auto_generated=True`) is the coordinator's sketch: it is
> excluded from the volunteer's own shift list and from the reminder sweep, cannot
> be acknowledged, and is deleted wholesale by `clear_draft`. `publish_draft` is
> what makes one real — it flips the flag, DMs the volunteer with the
> acknowledgment button, and emits `volunteer.assigned` per row.

`docs/reference/frontend.md`, the Volunteer hub section
([`:216`](../../../docs/reference/frontend.md)): update the `my_shifts_tab`
paragraph for the provenance caption, and the coordinator grid's description for
the draft banner.

### Verify

`poetry run python scripts/seed_dev.py` twice (idempotency), then confirm as
`staff_user` that day 2 shows one outlined chip and as `player_three` that My
Shifts does not list it.
