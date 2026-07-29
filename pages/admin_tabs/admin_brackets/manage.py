"""Manage dialog — roster, per-stage enrollment, seeding, round chrome, start.

The authoring half of the bracket admin. Everything here is presentation: it
reads through :class:`~application.services.bracket_service.BracketService` and
writes through it too, surfacing service ``ValueError`` / ``PermissionError`` as
toasts. Every scoped read runs inside ``tenant_scope`` because the dialog opens
from a detached client event that has lost the tenant contextvar.
"""

from typing import Dict

from nicegui import ui

from application.services import UserService
from application.tenant_context import tenant_scope
from models import BracketState
from theme.dialog._helpers import dialog_actions, form_dialog, submit_on_enter
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.notify import notify_error
from theme.tables.admin_crud import current_actor

from .shared import (
    distinct_rounds,
    iso_to_local_input,
    local_input_to_iso,
    round_editor_label,
)


async def open_manage(row, client, *, service, tenant_id, tournament_id, on_change) -> None:
    """Open the manage dialog for one stage. ``on_change`` refreshes the table."""
    bracket_id = row['id']
    tid = tournament_id
    with client:
        actor = await current_actor()
        # Fetched once for the whole dialog: the link picker is rebuilt on every
        # refresh, and re-reading the user list per refresh would be a query per
        # entrant added.
        users = await UserService().get_all_users()
        user_names = {u.id: u.preferred_name or u.username for u in users}
        # form_dialog, not a bare ui.dialog: it brings the house chrome — a
        # full-screen sheet on a phone plus a sticky header — and the action bar
        # below is sticky with it. Hand-rolled, this dialog put 'Start bracket'
        # and 'Close' ~1200-4400px below the fold.
        with form_dialog(f"Manage — {row['name']} · stage {row['stage_order']}") as dialog:

            @ui.refreshable
            async def body() -> None:
                with tenant_scope(tenant_id):
                    bracket = await service.get_bracket(bracket_id)
                    entrants = await service.list_entrants(tid)
                    entries = await service.list_entries(bracket_id)
                    matches = await service.list_matches(bracket_id)
                if bracket is None:
                    ui.label('Bracket not found.').classes('text-error')
                    return
                is_draft = bracket.state == BracketState.DRAFT
                enrolled_entrant_ids = {e.entrant_id for e in entries}
                entrant_by_id = {en.id: en for en in entrants}
                unlinked = [
                    entrant_by_id[e.entrant_id]
                    for e in entries
                    if e.entrant_id in entrant_by_id
                    and entrant_by_id[e.entrant_id].user_id is None
                ]

                # The state is what decides which half of this dialog is live, so
                # it is stated rather than left to be inferred from which buttons
                # happen to be disabled.
                with ui.row().classes('items-center gap-2 w-full'):
                    ui.badge(
                        bracket.state.value.upper(),
                        color={'draft': 'grey', 'active': 'positive'}.get(
                            bracket.state.value, 'secondary',
                        ),
                    )
                    ui.label(
                        'Enrollment and seeding are open.' if is_draft else
                        'The match graph is generated — enrollment and seeding are '
                        'locked. Round settings and user links can still be changed.'
                    ).classes('text-caption text-grey col min-w-0')

                async def link_user(entrant) -> None:
                    """Attach (or detach) one entrant's user account."""
                    with form_dialog(f'Link user — {entrant.display_name}') as link_dialog:
                        picker = ui.select(
                            user_names, value=entrant.user_id, label='User',
                            with_input=True,
                        ).props('clearable').classes('w-full')
                        ui.label(
                            'A linked entrant can be scheduled, DMed their matchup '
                            'and joined to a race room. An unlinked one is a name on '
                            'a bracket and nothing else.'
                        ).classes('text-caption text-grey')

                        async def save_link() -> None:
                            with tenant_scope(tenant_id):
                                try:
                                    await service.set_entrant_user(
                                        actor, entrant.id,
                                        int(picker.value) if picker.value else None,
                                    )
                                except (ValueError, PermissionError) as ex:
                                    notify_error(ex)
                                    return
                            ui.notify('Entrant link updated', color='positive')
                            link_dialog.close()
                            await body.refresh()

                        with dialog_actions().classes('justify-end'):
                            ui.button('Cancel', on_click=link_dialog.close).props('flat')
                            ui.button('Save', icon='link', on_click=save_link).props('color=primary')
                        submit_on_enter(link_dialog, save_link)
                    link_dialog.open()

                # --- roster ------------------------------------------------
                async def import_roster() -> None:
                    with tenant_scope(tenant_id):
                        try:
                            created = await service.import_entrants_from_roster(actor, tid)
                        except (ValueError, PermissionError) as ex:
                            notify_error(ex)
                            return
                    if created:
                        ui.notify(f'Imported {len(created)} entrant(s)', color='positive')
                    else:
                        ui.notify(
                            'Every enrolled player is already on the roster',
                            color='info',
                        )
                    await body.refresh()

                with ui.row().classes('items-center gap-2 w-full'):
                    ui.label('Add entrant to tournament').classes('section-title col min-w-0')
                    ui.button(
                        'Import roster', icon='group_add', on_click=import_roster,
                    ).props('flat dense color=primary').tooltip(
                        "Adds every player enrolled in this tournament who isn't "
                        'already an entrant, each linked to their account'
                    )

                with ui.row().classes('items-end gap-2 w-full'):
                    name_in = ui.input('Display name').classes('col-12 col-sm')
                    # A picker over preferred names, not the raw User.id this
                    # field used to ask for: that id is displayed by no screen in
                    # the app, so only someone with database access could fill it.
                    user_in = ui.select(
                        user_names, label='User (optional)', with_input=True,
                    ).props('clearable').classes('col-12 col-sm')

                    async def add_entrant() -> None:
                        picked = int(user_in.value) if user_in.value else None
                        with tenant_scope(tenant_id):
                            try:
                                await service.add_entrant(
                                    actor, tid,
                                    (name_in.value or '').strip()
                                    or user_names.get(picked, ''),
                                    picked,
                                )
                            except (ValueError, PermissionError) as ex:
                                notify_error(ex)
                                return
                        ui.notify('Entrant added', color='positive')
                        await body.refresh()

                    ui.button('Add', icon='person_add', on_click=add_entrant).props('color=primary')

                ui.separator()
                ui.label('Roster — enroll into this stage').classes('section-title')
                if not entrants:
                    ui.label('No entrants yet.').classes('text-muted')
                for en in entrants:
                    with ui.row().classes('items-center gap-2 w-full no-wrap'):
                        # `col min-w-0 ellipsis`: a long display name otherwise
                        # pushed the seed field and Enroll onto a second line on
                        # every phone-width row.
                        ui.label(en.display_name).classes('text-bold col min-w-0 ellipsis')
                        linked = en.user_id is not None
                        ui.button(
                            icon='link' if linked else 'link_off',
                            on_click=lambda _=None, entrant=en: link_user(entrant),
                        ).props(
                            'flat round dense color=' + ('positive' if linked else 'warning')
                        ).tooltip(
                            f'Linked to {user_names.get(en.user_id, "a user")}' if linked
                            else 'Not linked to a user — cannot be scheduled or notified'
                        )
                        if en.id in enrolled_entrant_ids:
                            ui.badge('enrolled', color='positive')
                        else:
                            seed_in = ui.number('Seed', min=1, precision=0) \
                                .props('inputmode=numeric dense' + ('' if is_draft else ' disable')) \
                                .classes('w-24')

                            async def enroll(_=None, entrant_id=en.id, seed_widget=seed_in) -> None:
                                with tenant_scope(tenant_id):
                                    try:
                                        await service.enroll(
                                            actor, bracket_id, entrant_id,
                                            int(seed_widget.value) if seed_widget.value else None,
                                        )
                                    except (ValueError, PermissionError) as ex:
                                        notify_error(ex)
                                        return
                                ui.notify('Enrolled', color='positive')
                                await body.refresh()

                            ui.button(
                                'Enroll', icon='how_to_reg', on_click=enroll,
                            ).props('flat color=primary' + ('' if is_draft else ' disable'))

                # --- enrolled entries / seeding ----------------------------
                ui.separator()
                ui.label('Enrolled entries').classes('section-title')
                if not entries:
                    ui.label('Nobody enrolled yet.').classes('text-muted')
                if entries and not is_draft:
                    ui.label(
                        'Seeding is fixed once the graph is generated.'
                    ).classes('text-caption text-grey')
                if unlinked:
                    ui.label(
                        f'{len(unlinked)} enrolled entrant(s) have no linked user: '
                        + ', '.join(en.display_name for en in unlinked)
                        + '. Their matches cannot be scheduled, announced or run in '
                        'a race room until they are linked.'
                    ).classes('text-caption text-warning')
                name_by_entrant = {en.id: en.display_name for en in entrants}
                seed_widgets: Dict[int, object] = {}
                for entry in entries:
                    with ui.row().classes('items-center gap-2 w-full no-wrap'):
                        ui.label(
                            name_by_entrant.get(entry.entrant_id, f'Entry {entry.id}')
                        ).classes('col min-w-0 ellipsis')
                        seed_widgets[entry.id] = ui.number(
                            'Seed', value=entry.seed, min=1, precision=0,
                        ).props(
                            'inputmode=numeric dense' + ('' if is_draft else ' disable')
                        ).classes('w-24')

                async def save_seeds() -> None:
                    seeds = {
                        eid: int(w.value)
                        for eid, w in seed_widgets.items()
                        if w.value is not None
                    }
                    with tenant_scope(tenant_id):
                        try:
                            await service.set_seeds(actor, bracket_id, seeds)
                        except (ValueError, PermissionError) as ex:
                            notify_error(ex)
                            return
                    ui.notify('Seeds saved', color='positive')
                    await body.refresh()

                async def do_start() -> None:
                    with tenant_scope(tenant_id):
                        try:
                            await service.start_bracket(actor, bracket_id)
                        except (ValueError, PermissionError) as ex:
                            notify_error(ex)
                            return
                    ui.notify('Bracket started', color='positive')
                    await body.refresh()
                    await on_change()

                async def start() -> None:
                    """Confirm before the one authoring step that cannot be undone.

                    Start is the draw, the publish and the notification at once:
                    afterwards the stage can no longer be edited, reseeded or
                    deleted, and every entrant has already been told their opening
                    matchup.
                    """
                    message = (
                        f'Start “{bracket.name}”? This generates the match graph from '
                        f'the current seeding, publishes the stage publicly, and '
                        f'notifies {len(entries)} entrant(s) of their opening matchup. '
                        'Seeds cannot be changed and the stage cannot be edited or '
                        'deleted afterwards.'
                    )
                    if unlinked:
                        message += (
                            f' {len(unlinked)} of them have no linked user account, so '
                            'their matches cannot be scheduled or announced.'
                        )

                    async def confirmed() -> None:
                        confirm.dialog.close()
                        await do_start()

                    confirm = ConfirmationDialog(
                        message, on_confirm=confirmed, confirm_text='Start bracket',
                    )
                    confirm.open()

                # Per-round display metadata (best-of / scheduled time) — editable
                # in any state (it never touches the graph).
                rounds = distinct_rounds(matches)
                if rounds:
                    rounds_cfg = (bracket.config or {}).get('rounds') or {}
                    widgets: Dict[int, tuple] = {}
                    with ui.expansion('Round settings — best-of & scheduled time') \
                            .classes('w-full q-mt-sm'):
                        ui.label(
                            'Best-of is the series length the round is actually '
                            'played at, not just a label (time is Eastern).'
                        ).classes('text-caption text-grey')
                        for r in rounds:
                            cfg = rounds_cfg.get(str(r)) or {}
                            # The round name takes its own line on a phone (a fixed
                            # w-32 label left the two inputs too little room and the
                            # row wrapped anyway).
                            with ui.row().classes('items-center gap-2 w-full'):
                                ui.label(round_editor_label(r)) \
                                    .classes('col-12 col-sm-3 text-bold')
                                bo = ui.number(
                                    'Best of', value=cfg.get('best_of'), min=1, precision=0,
                                ).props('dense inputmode=numeric').classes('col-4 col-sm-3')
                                sched = ui.input(
                                    'Scheduled (ET)',
                                    value=iso_to_local_input(cfg.get('scheduled_at')),
                                ).props('type=datetime-local dense').classes('col')
                                widgets[r] = (bo, sched)

                        async def save_rounds() -> None:
                            new_rounds: Dict[str, dict] = {}
                            for r, (bo, sched) in widgets.items():
                                entry: Dict[str, object] = {}
                                if bo.value:
                                    entry['best_of'] = int(bo.value)
                                iso = local_input_to_iso(sched.value)
                                if iso:
                                    entry['scheduled_at'] = iso
                                if entry:
                                    new_rounds[str(r)] = entry
                            with tenant_scope(tenant_id):
                                try:
                                    await service.set_round_metadata(
                                        actor, bracket_id, new_rounds or None,
                                    )
                                except (ValueError, PermissionError) as ex:
                                    notify_error(ex)
                                    return
                            ui.notify('Round settings saved', color='positive')
                            await body.refresh()

                        ui.button(
                            'Save round settings', icon='save', on_click=save_rounds,
                        ).props('flat color=primary')

                with dialog_actions().classes('justify-end'):
                    if is_draft and entries:
                        ui.button('Save seeds', icon='save', on_click=save_seeds).props('flat color=primary')
                        ui.button('Start bracket', icon='play_arrow', on_click=start).props('color=primary')
                    ui.button('Close', on_click=dialog.close).props('flat')

            await body()
        dialog.open()
