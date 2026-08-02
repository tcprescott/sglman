

from nicegui import app, ui

from application.services import (
    BracketService,
    ChallongeService,
    FeatureFlagService,
    MatchRescheduleService,
    MatchService,
    TournamentService,
    get_user_from_discord_id,
)
from application.utils.timezone import format_local_display
from models import FeatureFlag, RescheduleRequestKind, RescheduleRequestStatus
from theme.dialog.bracket_schedule_dialog import BracketScheduleDialog
from theme.dialog.challonge_schedule_dialog import ChallongeScheduleDialog
from theme.dialog.match_dialog import UserMatchDialog
from theme.dialog.reschedule_request_dialog import RescheduleRequestDialog
from theme.help import help_icon
from theme.tables.match import MatchTableView
from theme.tables.match_slots import SEED_SLOT_READONLY, state_readonly_slot
from theme.tables.preferences import TableKeys


def _next_game_number(bracket_match, best_of: int) -> int:
    """The slot the service would allocate next — for labelling only.

    ``list_open_matches_for_user`` only returns matchups with a slot free, so the
    fallback is unreachable; it keeps the label sane rather than raising in a
    render pass if that ever changes.
    """
    taken = {g.game_number for g in bracket_match.games}
    return next((n for n in range(1, best_of + 1) if n not in taken), best_of)


def _notify_stale_schedule_link() -> None:
    """Say why a "Pick a time" button did nothing.

    A DM outlives the matchup it points at — the opponent may have booked it,
    staff may have scheduled it, the stage may have finished. Landing on a page
    where the row simply is not there reads as a broken link, so the reason is
    said out loud.
    """
    ui.notify(
        'That matchup is no longer waiting to be scheduled.', color='warning',
    )


def _report_stale_deep_link(deep_link: dict) -> None:
    """The same notice for the case where the viewer has no open matchups at all."""
    if deep_link.pop('matchup_id', None) is not None:
        _notify_stale_schedule_link()


def _notify_stale_reschedule_link() -> None:
    """Say why an "Ask again" button did nothing.

    A DM outlives the match it points at: staff may have moved it anyway, it may
    have been played, or the tournament may have stopped taking requests. Landing
    on a page with no dialog reads as a broken link, so the reason is said aloud.
    """
    ui.notify(
        "That match can't be changed any more.", color='warning',
    )


# What each status means to the person who asked, rather than the machine key.
_REQUEST_STATUS = {
    RescheduleRequestStatus.PENDING: ('Waiting on staff', 'warning'),
    RescheduleRequestStatus.APPROVED: ('Approved', 'positive'),
    RescheduleRequestStatus.DECLINED: ('Declined', 'negative'),
    RescheduleRequestStatus.WITHDRAWN: ('You withdrew this', 'grey'),
    # Named from the reader's side: "superseded" is our word, not theirs.
    RescheduleRequestStatus.SUPERSEDED: ('Settled by another request', 'grey'),
}


def _render_request_card(row, *, on_withdraw) -> None:
    """One request, its status, and staff's reply if they left one."""
    label, colour = _REQUEST_STATUS.get(row.status, (row.status, 'grey'))
    cancel = row.kind is RescheduleRequestKind.CANCEL
    with ui.column().classes('full-width gap-1 q-my-sm'):
        with ui.row().classes('items-center gap-2 full-width'):
            ui.label(row.match.tournament.name).classes('text-bold')
            ui.badge(label, color=colour)
        ui.label(
            'Asked to call it off' if cancel
            else f'Asked to move it to {format_local_display(row.proposed_at)}'
            if row.proposed_at else 'Asked to move it, staff to pick a time'
        ).classes('text-caption text-grey-7')
        ui.label(f'Your reason: {row.reason}').classes('text-caption text-grey-7')
        if row.decision_note:
            ui.label(f'Staff said: {row.decision_note}')
        if row.status is RescheduleRequestStatus.PENDING:
            if row.opponent_agreed_at:
                ui.label('Your opponent agreed.').classes('text-caption text-positive')

            async def withdraw(_=None, request_id=row.id):
                from application.services import MatchRescheduleService
                from application.services import get_user_from_discord_id as _get

                actor = await _get(app.storage.user.get('discord_id'))
                try:
                    await MatchRescheduleService().withdraw(request_id, actor)
                except (ValueError, PermissionError) as e:
                    ui.notify(str(e), color='warning')
                    return
                ui.notify('Withdrawn.', color='positive')
                on_withdraw()

            ui.button('Withdraw', icon='undo', on_click=withdraw) \
                .props('flat dense color=grey size=sm')
    ui.separator()


def _round_label(bracket_match, best_of: int, number: int) -> str:
    """'Round 2' / 'Losers round 1', plus the series position for a best-of-N."""
    rnd = bracket_match.round
    base = f'Losers round {abs(rnd)}' if rnd < 0 else f'Round {rnd}'
    return f'{base} — game {number} of {best_of}' if best_of > 1 else base


async def render_player_dashboard(
    schedule: int | None = None, reschedule: int | None = None,
):
    """The player's own schedule.

    ``schedule`` is a bracket matchup id arriving from the "matchup ready to
    schedule" DM's button (``?schedule=<id>`` on ``/home/player``). Its dialog is
    opened once the tab has rendered, so the notification's call to action ends
    at the date/time picker instead of at a page the reader then has to search.

    ``reschedule`` is a match id doing the same for the declined-request DM:
    its "Ask again" button lands on the request form for that match, because
    asking again with a different time is the actual next step after a refusal.
    """
    discord_id = app.storage.user.get('discord_id', None)
    # Resolved once for the help icons below: three of them read from the event
    # handbook, which filters by role, and each would otherwise look the viewer
    # up for itself.
    viewer = await get_user_from_discord_id(discord_id)
    match_service = MatchService()
    reschedule_service = MatchRescheduleService()
    challonge_service = ChallongeService()
    bracket_service = BracketService()
    
    with ui.column().classes('page-container'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Your Schedule').classes('page-title')
            await help_icon('player-schedule', user=viewer)
            await help_icon('stream-volunteer', label='Stream', user=viewer)
            await help_icon('reschedule-request', label='Change', user=viewer)
            await help_icon('check-in', label='Check-in', user=viewer)
            await help_icon('player-room', label='In the room', user=viewer)
            await help_icon('player-stage', label='On a stage', user=viewer)
            ui.space()
            if not discord_id:
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary')
        
        ui.separator().classes('separator-spacing')
        
        if not discord_id:
            with ui.card().classes('card-centered'):
                ui.icon('lock', size='3em').classes('icon-large')
                ui.label('You must be logged in to view this page.').classes('text-muted')
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary size=lg')
            return

        # Challonge: upcoming bracket matches the player can schedule in a few clicks.
        @ui.refreshable
        async def challonge_section():
            # Credentials *and* the community's flag: the service refuses the
            # listing below without the feature, and this tab isn't flag-gated.
            if not challonge_service.is_configured():
                return
            if not await FeatureFlagService().is_enabled(FeatureFlag.CHALLONGE):
                return
            user = await get_user_from_discord_id(discord_id)
            if user is None:
                return
            matches = await challonge_service.list_unscheduled_matches_for_user(user)
            if not matches:
                return
            # The refreshable renders into its own container, so create elements
            # directly (there is no separate challonge_container to enter).
            with ui.card().classes('card-full-width'):
                ui.label('Upcoming matches to schedule').classes('section-title')
                ui.label('From your Challonge bracket. Pick a time and your opponent confirms.').classes(
                    'text-caption text-grey-7'
                )
                for cm in matches:
                    me_is_p1 = cm.participant1 is not None and cm.participant1.user_id == user.id
                    opponent = cm.participant2 if me_is_p1 else cm.participant1
                    opponent_name = opponent.name if opponent else 'TBD'
                    opponent_linked = opponent is not None and opponent.user_id is not None
                    with ui.row().classes('items-center full-width q-my-xs'):
                        ui.label(cm.tournament.name).classes('text-bold')
                        ui.label(f'vs {opponent_name}')
                        if cm.round is not None:
                            ui.label(f'Round {cm.round}').classes('text-caption text-grey-7')
                        ui.space()
                        if opponent_linked:
                            async def do_schedule(_=None, m=cm, oname=opponent_name):
                                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))

                                async def after():
                                    challonge_section.refresh()
                                    await table_view.refresh()

                                dialog = ChallongeScheduleDialog(
                                    m, actor=actor, opponent_name=oname, on_submit=after,
                                )
                                await dialog.open()

                            ui.button('Schedule', icon='event', on_click=do_schedule).props('color=primary flat')
                        else:
                            disabled_btn = ui.button('Schedule', icon='event').props('flat color=primary')
                            disabled_btn.disable()
                            disabled_btn.tooltip("Waiting for your opponent to link their Challonge account")

        # The deep-linked matchup's opener, captured during the render below so
        # `?schedule=<id>` can fire the same handler the button does. Per-client
        # (a local, never module level) and cleared once used, so a later refresh
        # of the section does not re-open the dialog under the reader.
        deep_link = {'matchup_id': schedule}

        # Native brackets: the *only* scheduling route in a bracket-run
        # tournament, since those turn off manual match requests.
        @ui.refreshable
        async def bracket_section():
            if not await FeatureFlagService().is_enabled(FeatureFlag.BRACKETS):
                return
            user = await get_user_from_discord_id(discord_id)
            if user is None:
                return
            matchups = await bracket_service.list_open_matches_for_user(user.id)
            if not matchups:
                _report_stale_deep_link(deep_link)
                return
            openers: dict = {}
            with ui.card().classes('card-full-width'):
                ui.label('Upcoming matches to schedule').classes('section-title')
                ui.label('From your bracket. Pick a time and your opponent confirms.').classes(
                    'text-caption text-grey-7'
                )
                for bm in matchups:
                    me_is_e1 = bm.entry1.entrant.user_id == user.id
                    opponent = bm.entry2 if me_is_e1 else bm.entry1
                    opponent_name = opponent.entrant.display_name
                    best_of = bracket_service.resolve_best_of(bm.bracket, bm)
                    number = _next_game_number(bm, best_of)
                    # Name/matchup stack beside the action, rather than one flat
                    # row: on a phone the flat row wrapped into a ragged three
                    # lines with the ui.space() stranded mid-block.
                    with ui.row().classes(
                        'items-center justify-between full-width q-my-xs gap-2'
                    ):
                        with ui.column().classes('col min-w-0 gap-0'):
                            # `ellipsis` on each line: a long tournament name
                            # otherwise wraps to three lines on a phone once the
                            # action button has taken its width.
                            ui.label(bm.bracket.tournament.name) \
                                .classes('text-bold ellipsis')
                            ui.label(f'vs {opponent_name}').classes('ellipsis')
                            ui.label(_round_label(bm, best_of, number)) \
                                .classes('text-caption text-grey-7 ellipsis')

                        async def do_schedule(_=None, m=bm, oname=opponent_name,
                                              n=number, bo=best_of):
                            actor = await get_user_from_discord_id(
                                app.storage.user.get('discord_id')
                            )

                            async def after():
                                bracket_section.refresh()
                                await table_view.refresh()

                            await BracketScheduleDialog(
                                m.id, actor,
                                opponent_name=oname,
                                game_number=n,
                                best_of=bo,
                                tournament_name=m.bracket.tournament.name,
                                tournament_id=m.bracket.tournament_id,
                                player_ids=[
                                    m.entry1.entrant.user_id,
                                    m.entry2.entrant.user_id,
                                ],
                                on_submit=after,
                            ).open()

                        openers[bm.id] = do_schedule
                        ui.button(
                            f'Schedule game {number}' if best_of > 1 else 'Schedule',
                            icon='event', on_click=do_schedule,
                        ).props('color=primary flat')

            # `openers` only holds this viewer's own open matchups — the listing
            # is already scoped to them — so an id from a forwarded link cannot
            # open someone else's dialog; it falls through to the stale notice.
            matchup_id = deep_link.pop('matchup_id', None)
            if matchup_id is not None:
                opener = openers.get(int(matchup_id))
                if opener is not None:
                    await opener()
                else:
                    _notify_stale_schedule_link()

        columns = [
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament',
             'sortable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at',
             'sortable': True},
            {'name': 'state', 'label': 'State', 'field': 'state', 'sortable': True},
            # Not sortable: a joined roster of names.
            {'name': 'players', 'label': 'Players', 'field': 'players'},
            {'name': 'stage', 'label': 'Stage', 'field': 'stage',
             'sortable': True},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
            # Beside Watch, because both are this viewer acting on their own
            # behalf rather than reading the match. Offering is advisory — the
            # cell's tooltip and the confirmation both say so.
            {'name': 'stream_volunteer', 'label': 'Stream', 'field': 'stream_volunteer'},
            # Beside Stream for the same reason: this viewer acting on their own
            # behalf rather than reading the match.
            {'name': 'reschedule', 'label': 'Change', 'field': 'reschedule'},
            {'name': 'watch', 'label': 'Watch', 'field': 'watch'},
        ]

        extra_slots = {
            'body-cell-state': state_readonly_slot(scheduled_detailed=False),
            'body-cell-generated_seed': SEED_SLOT_READONLY,
        }

        async def submit_match():
            dialog = UserMatchDialog(discord_id=discord_id)
            await dialog.open()

        async def get_query():
            return await match_service.get_matches_for_player(discord_id)

        # Request Match only where a request can actually be made. The dialog's
        # own dead end — "your tournaments are scheduled from their bracket" —
        # is the right message once you are in it, but a button that exists only
        # to explain that it does nothing is a button that should not be there.
        # Same list the dialog offers, so the two cannot disagree.
        can_request = bool(
            viewer is not None
            and await TournamentService().list_player_requestable(viewer)
        )

        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False,
            table_key=TableKeys.HOME_PLAYER_MATCHES,
            submit_match_callback=submit_match if can_request else None,
            extra_slots=extra_slots,
            player_discord_id=discord_id,
            storage_key='player_dashboard',
        )
        @ui.refreshable
        async def requests_section():
            """This viewer's own reschedule requests, and what became of them.

            Cards rather than a table: three or four rows of prose, one of which
            is staff's reply, read badly in cells and would drag the column
            preferences machinery along for no gain.

            Without this a player who asked has no way to learn whether anyone
            answered — the same loop ``FeedbackService.list_mine`` closes.
            """
            if viewer is None:
                return
            rows = await reschedule_service.list_mine(viewer)
            if not rows:
                return
            with ui.card().classes('card-full-width'):
                ui.label('Your change requests').classes('section-title')
                for row in rows:
                    _render_request_card(row, on_withdraw=requests_section.refresh)

        async def _open_reschedule(match_id: int) -> None:
            """Open the request form for one match, from the declined DM's button."""
            match = await match_service.get_by_id(match_id)
            if match is None or viewer is None:
                _notify_stale_reschedule_link()
                return
            if not await reschedule_service.can_request(match, viewer):
                _notify_stale_reschedule_link()
                return

            async def after():
                requests_section.refresh()
                await table_view.refresh()

            await RescheduleRequestDialog(match, viewer, on_submit=after).open()

        await challonge_section()
        await bracket_section()
        await requests_section()
        if reschedule is not None:
            await _open_reschedule(int(reschedule))
        # No initial refresh here: MatchTableView._initial_load owns it, and runs
        # after the stored filters are restored rather than racing them.

