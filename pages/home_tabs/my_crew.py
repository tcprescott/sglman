"""My Crew — a volunteer's own commentator and tracker commitments.

The crew loop had a surface for the admin (the Schedule board's cells) and none
for the person doing the work. After signing up, their only handle on the
commitment was a Withdraw button in one row of a shared, chronologically-sorted
board — 17 rows and ~5,900 px of scroll on a phone — and their only reminder was
the approval DM, if approval ever happened. The Player tab ("Your Schedule") is
players-only and mentions crew nowhere.

Modelled on **My Shifts** (``pages/volunteer_tabs/my_shifts.py``), deliberately: the
same people do both kinds of work, and shifts have had this page all along.
Lives on Home rather than the Volunteer hub because crew signup is neither
role-gated nor behind ``FeatureFlag.VOLUNTEERS`` — anyone in the community can
sign up from the Schedule board, so anyone must be able to see what they signed
up for.
"""

from typing import Any

from nicegui import app, background_tasks, context, ui

from application.services import CrewService, get_user_from_discord_id
from application.utils.match_labels import match_label
from application.utils.timezone import format_local_display
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.notify import notify_error
from theme.section import section_panel


def commitment_status(row: dict) -> tuple[str, str]:
    """``(chip class, label)`` for one commitment — the four states it can be in.

    Pure so the vocabulary is testable without a browser, and so the page and
    any future Discord/report mirror cannot describe the same row differently.
    """
    if row.get('finished'):
        return 'wiz-chip--neutral', 'Played'
    if not row.get('approved'):
        return 'wiz-chip--pending', 'Awaiting approval'
    if not row.get('acknowledged'):
        return 'wiz-chip--candidate', 'Approved — please confirm'
    return 'wiz-chip--ok', 'Confirmed'


def commitment_title(row: dict) -> str:
    """The match, named the way the person looking at it would name it.

    Reads through ``match_labels`` for the reason that module exists: an id in a
    sentence is a defect wherever a user can read it.
    """
    return match_label(
        player_names=row.get('players') or [],
        tournament=row.get('tournament') or '',
        scheduled_at=format_local_display(row.get('scheduled_at')),
    )


async def my_crew_tab() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if user is None:
        ui.label('You must be logged in to see your crew commitments.').classes('text-error')
        return

    service = CrewService()
    state = {'upcoming_only': True}

    panel = await section_panel(
        'Crew you signed up for',
        icon='headset_mic',
        subtitle='Commentary and tracking slots you volunteered for.',
        help_topics=[
            'crew-status',
            ('crew-approval', 'Approval'),
            ('crew-withdraw', 'Withdrawing'),
        ],
        user=user,
    )
    page = panel.body
    with page:
        # ``client`` arrives from the call site, never read in here: both of
        # these run as detached background tasks, where the slot stack is empty
        # and ``context.client`` *raises* rather than returning None. Reading it
        # on the first line meant both buttons died before doing anything —
        # the volunteer's Confirm and Withdraw were dead controls.
        async def withdraw(row: dict, client) -> None:
            dialog: Any = None  # bound below; ConfirmationDialog.dialog exists after open()

            async def perform() -> None:
                # The confirm handler is itself a detached task, so it needs the
                # same client the opener was handed.
                with client:
                    try:
                        await service.undo_crew_signup(row['match_id'], user, row['role'])
                        ui.notify(
                            f'You have been removed as a {row["role"]}.', color='positive')
                    except (ValueError, PermissionError) as e:
                        notify_error(e)
                    await commitments.refresh()

            # The two withdrawals are not the same act: dropping a slot staff
            # approved and announced costs them cover, and the service tells
            # them so. Same split the board's Withdraw makes.
            if row['approved']:
                message = (
                    f'Withdraw as {row["role"]} for {commitment_title(row)}?\n\n'
                    'Staff approved you for this slot — they will be told you have '
                    'withdrawn so they can find cover.'
                )
                tone = 'negative'
            else:
                message = f'Withdraw as {row["role"]} for {commitment_title(row)}?'
                tone = 'primary'

            with page:
                dialog = ConfirmationDialog(
                    message,
                    title=f'Withdraw as {row["role"]}',
                    confirm_text='Withdraw',
                    tone=tone,
                    on_confirm=lambda: background_tasks.create(perform()),
                )
                dialog.open()

        async def acknowledge(row: dict, client) -> None:
            # Everything inside the client, not just the notify: the service
            # call and the refresh are both tenant-scoped reads, and the stash
            # the tenant fallback reads only exists within this block.
            with client:
                try:
                    await service.acknowledge_crew_assignment(row['id'], row['role'], user)
                    ui.notify('Thanks — your slot is confirmed.', color='positive')
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                await commitments.refresh()

        @ui.refreshable
        async def commitments() -> None:
            rows = await service.list_my_commitments(
                user, upcoming_only=state['upcoming_only'])
            if not rows:
                ui.label(
                    'Nothing yet. Sign up to commentate or track a match from the '
                    'Schedule tab.'
                ).classes('text-muted')
                return
            for row in rows:
                chip_class, status = commitment_status(row)
                with ui.card().classes('full-width q-mb-sm'):
                    with ui.row().classes('items-center gap-2 flex-wrap full-width'):
                        with ui.element('span').classes(f'wiz-chip {chip_class}'):
                            ui.label(status)
                        ui.label(row['role'].capitalize()).classes('text-weight-medium')
                        ui.space()
                        if row['stage']:
                            with ui.element('span').classes('wiz-chip wiz-chip--neutral'):
                                ui.icon('tv', size='14px')
                                ui.label(row['stage'])
                    ui.label(commitment_title(row)).classes('text-body2')
                    with ui.row().classes('items-center gap-2'):
                        # Acknowledging from here is the same act the approval
                        # DM's button performs; a volunteer who missed the DM
                        # had no other way to do it.
                        if row['approved'] and not row['acknowledged'] and not row['finished']:
                            ui.button(
                                'Confirm I can cover this', icon='check',
                                on_click=lambda _e, r=row: background_tasks.create(
                                    acknowledge(r, context.client)),
                            ).props('color=primary dense no-caps')
                        if not row['finished']:
                            ui.button(
                                'Withdraw', icon='undo',
                                on_click=lambda _e, r=row: background_tasks.create(
                                    withdraw(r, context.client)),
                            ).props('flat color=negative dense no-caps')

        async def toggle_scope(event) -> None:
            state['upcoming_only'] = not bool(event.value)
            await commitments.refresh()

        # In the header rather than above the list: a scope switch floating over
        # the cards it filters reads as a stray control on a stacked page.
        with panel.aside:
            ui.switch('Include past', value=False, on_change=toggle_scope) \
                .props('dense').classes('wiz-panel__switch') \
                .tooltip('Show matches that have already been played')

        await commitments()
