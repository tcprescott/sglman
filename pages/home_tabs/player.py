

from nicegui import app, ui

from application.services import (
    BracketService,
    ChallongeService,
    FeatureFlagService,
    MatchService,
    get_user_from_discord_id,
)
from models import FeatureFlag
from theme.dialog.bracket_schedule_dialog import BracketScheduleDialog
from theme.dialog.challonge_schedule_dialog import ChallongeScheduleDialog
from theme.dialog.match_dialog import UserMatchDialog
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


def _round_label(bracket_match, best_of: int, number: int) -> str:
    """'Round 2' / 'Losers round 1', plus the series position for a best-of-N."""
    rnd = bracket_match.round
    base = f'Losers round {abs(rnd)}' if rnd < 0 else f'Round {rnd}'
    return f'{base} — game {number} of {best_of}' if best_of > 1 else base


async def render_player_dashboard():
    discord_id = app.storage.user.get('discord_id', None)
    match_service = MatchService()
    challonge_service = ChallongeService()
    bracket_service = BracketService()
    
    with ui.column().classes('page-container'):
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Your Schedule').classes('page-title')
            await help_icon('player-schedule')
            await help_icon('check-in', label='Check-in')
            await help_icon('player-room', label='In the room')
            await help_icon('player-stage', label='On a stage')
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
                return
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

                        ui.button(
                            f'Schedule game {number}' if best_of > 1 else 'Schedule',
                            icon='event', on_click=do_schedule,
                        ).props('color=primary flat')

        columns = [
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament',
             'sortable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at',
             'sortable': True},
            {'name': 'state', 'label': 'State', 'field': 'state', 'sortable': True},
            # Not sortable: a joined roster of names.
            {'name': 'players', 'label': 'Players', 'field': 'players'},
            {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room',
             'sortable': True},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed'},
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
        
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=False,
            table_key=TableKeys.HOME_PLAYER_MATCHES,
            submit_match_callback=submit_match,
            extra_slots=extra_slots,
            player_discord_id=discord_id,
            storage_key='player_dashboard',
        )
        await challonge_section()
        await bracket_section()
        # No initial refresh here: MatchTableView._initial_load owns it, and runs
        # after the stored filters are restored rather than racing them.

