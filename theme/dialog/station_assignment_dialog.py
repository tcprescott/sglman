"""Station Assignment Dialog - Assign stations to match players"""

from typing import Callable, Optional

from nicegui import app, ui

from application.services import MatchService, StationService, get_user_from_discord_id
from application.services.system_config_service import SystemConfigService
from application.utils.match_labels import match_model_label
from models import STATION_REGEXES, Match
from theme.dialog._helpers import dialog_actions, mobile_sheet
from theme.notify import notify_error

# Copy for the dialog's two jobs. 'checkin' is the proctor's combined
# step 1 + 2 (seat the players, then check the match in); 'stations' is
# correcting the seating of a match that is already checked in.
_PURPOSE_COPY = {
    'checkin': {
        'title': 'Check in — {match}',
        'lead': 'Seat each player at a station, then check the match in.',
        'submit': 'Check in & seat',
    },
    'stations': {
        'title': 'Assign stations — {match}',
        'lead': 'Update the station each player is sitting at.',
        'submit': 'Save stations',
    },
}


class StationAssignmentDialog:
    """Dialog for assigning stations to players in a match."""

    def __init__(
        self,
        match: Match,
        on_submit: Optional[Callable] = None,
        *,
        purpose: str = 'stations',
    ):
        """
        Initialize the station assignment dialog.

        Args:
            match: The match with players to assign stations to
            on_submit: Optional callback when stations are assigned
            purpose: Which job the dialog is doing — ``'checkin'`` when the
                caller seats the match afterwards (and therefore owns the
                success toast), ``'stations'`` when this dialog is the whole
                job.
        """
        self.match = match
        self.on_submit = on_submit
        self.purpose = purpose if purpose in _PURPOSE_COPY else 'stations'
        self.match_service = MatchService()
        self.dialog = None
        self.station_inputs = {}  # Dict to store station input fields by player ID

    async def open(self):
        """Open the dialog and load match data."""
        # Ensure match has players and tournament loaded
        await self.match.fetch_related('tournament', 'players', 'players__user')
        fmt = await SystemConfigService.get_station_format()
        copy = _PURPOSE_COPY[self.purpose]

        # A community that has defined no stations keeps the historical
        # free-text field; once it has a pool, the proctor picks from it.
        stations = await StationService().list_stations(active_only=True)
        occupied = await self.match_service.occupied_stations_for_dialog(self.match.id)

        with ui.dialog() as self.dialog, ui.card().classes('dialog-card').style('max-width: 600px; width: 100%;'):
            mobile_sheet(self.dialog)
            # Header
            with ui.row().classes('dialog-header'):
                ui.label(
                    copy['title'].format(
                        match=match_model_label(self.match, with_context=False),
                    )
                ).classes('dialog-title')
                ui.space()
                ui.button(icon='close', on_click=self.dialog.close).props('flat round dense').tooltip('Close')
            
            ui.separator()
            
            # Match info
            with ui.column().classes('q-pa-md'):
                if self.match.tournament:
                    ui.label(f'Tournament: {self.match.tournament.name}').classes('text-subtitle1')
                
                if self.match.scheduled_at:
                    from application.utils.timezone import format_local_datetime
                    ui.label(f'Scheduled: {format_local_datetime(self.match.scheduled_at)}').classes('text-body2 text-grey-7')
            
            ui.separator()
            
            # Players and station assignments
            with ui.column().classes('q-pa-md q-gutter-md full-width'):
                if not self.match.players:
                    ui.label('No players assigned to this match').classes('text-grey-7')
                else:
                    with ui.row().classes('items-center full-width'):
                        ui.label(copy['lead']).classes('text-subtitle2')
                        ui.space()
                        # Only offered for a head-to-head: the draw's whole job
                        # is putting two players on opposite sides, and it
                        # refuses any other player count.
                        if len(self.match.players) == 2 and stations:
                            ui.button(
                                'Randomize',
                                icon='casino',
                                on_click=self._handle_randomize,
                            ).props('flat dense color=primary').tooltip(
                                'Draw a free station for each player, on opposite '
                                'sides of the room'
                            )


                    for player in self.match.players:
                        with ui.column().classes('q-gutter-xs full-width'):
                            # Player name
                            ui.label(player.user.preferred_name or player.user.username).classes('text-weight-medium')

                            # Station input (leave blank to clear assignment).
                            # ``occupied`` excludes this match, so a player's own
                            # current station never shows as taken.
                            if stations:
                                # An occupied station names the match sitting at
                                # it, not its id: the proctor's next move is to
                                # go and find those players, and "match #23"
                                # tells them nothing about who to look for.
                                options = {
                                    s.name: (
                                        f'{s.name} — in use ({occupied[s.name]})'
                                        if s.name in occupied
                                        else (f'{s.name} · {s.section}' if s.section else s.name)
                                    )
                                    for s in stations
                                }
                                # An assignment made before the pool existed (or
                                # to a since-removed station) would otherwise
                                # render as an empty select, hiding what the
                                # schedule row still shows.
                                if player.assigned_station and player.assigned_station not in options:
                                    options[player.assigned_station] = (
                                        f'{player.assigned_station} — not in the station pool'
                                    )
                                station_input = ui.select(
                                    options=options,
                                    label='Station',
                                    with_input=True,
                                    clearable=True,
                                ).props('outlined dense').classes('full-width')
                            else:
                                station_input = ui.input(
                                    label='Station',
                                    placeholder='e.g., A1, B2, Station 3',
                                    validation={'Invalid station format': lambda v: not v or STATION_REGEXES[fmt].fullmatch(v) is not None},
                                ).props('outlined dense maxlength=50').classes('full-width')

                            # Pre-fill existing station if available
                            if player.assigned_station:
                                station_input.value = player.assigned_station

                            # Store reference to input
                            self.station_inputs[player.id] = station_input
            
            # Action buttons
            with dialog_actions():
                ui.button('Cancel', on_click=self.dialog.close).props('flat')
                ui.button(copy['submit'], on_click=self._handle_submit).props('color=primary')
        
        self.dialog.open()
    
    async def _handle_randomize(self):
        """Fill the pickers with a drawn seating, without committing it.

        The proctor still submits, so a draw they dislike costs them a second
        click rather than a correction.
        """
        try:
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            suggestion = await self.match_service.suggest_stations(
                self.match.id, actor=actor,
            )
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return

        for player_id, station in suggestion.assignments.items():
            station_input = self.station_inputs.get(player_id)
            if station_input is None:
                continue
            # A drawn station is guaranteed to be in the active pool, but the
            # select only offers the options built when the dialog opened.
            if hasattr(station_input, 'options') and station not in station_input.options:
                station_input.options[station] = station
                station_input.update()
            station_input.value = station

        for note in suggestion.relaxations:
            ui.notify(note, color='warning')
        if not suggestion.relaxations:
            ui.notify('Seats drawn — opposite sides, nobody crowded.', color='positive')

    async def _handle_submit(self):
        """Handle station assignment submission."""
        try:
            assignments = {}
            for player_id, station_input in self.station_inputs.items():
                station = station_input.value.strip() if station_input.value else None
                assignments[player_id] = station

            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            await self.match_service.assign_stations(self.match.id, assignments, actor=actor)

            # In 'checkin' mode the caller still has to seat the match, so it
            # owns the success toast — saying "done" here would be premature.
            if self.purpose == 'stations':
                ui.notify(
                    f'Stations updated for '
                    f'{match_model_label(self.match, with_context=False)}.',
                    color='positive',
                )

            if self.on_submit:
                await self.on_submit(self.match)

            self.dialog.close()

        except (ValueError, PermissionError) as e:
            notify_error(e)
