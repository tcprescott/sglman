"""Shared behaviour for the admin and player match dialogs.

Split out of ``match_dialog.py`` when that module reached the 800-line
guideline; the two concrete dialogs still live there.
"""

from typing import Awaitable, Callable

from nicegui import app, background_tasks, context, ui

from application.services import (
    BracketService,
    CrewService,
    MatchService,
    MatchSuggestionService,
    MatchWatcherService,
    StreamRoomService,
    TournamentService,
    UserService,
    get_user_from_discord_id,
)
from application.utils.timezone import (
    format_eastern_date,
    format_eastern_time,
    now_eastern,
)
from models import Match
from theme.dialog._helpers import (
    dialog_actions,
    native_date_input,
    native_time_input,
    submit_on_enter,
)
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.notify import notify_error


def enrolment_preview(names: list, tournament_name: str) -> str:
    """The sentence naming who scheduling this match will enrol.

    Empty when everyone chosen is already an entrant, so it says nothing on the
    common path — the point is to surface a side effect, not to add noise.
    """
    if not names:
        return ''
    if len(names) == 1:
        return f'{names[0]} will be enrolled in {tournament_name}.'
    listed = ', '.join(names[:-1]) + f' and {names[-1]}'
    return f'{listed} will be enrolled in {tournament_name}.'


def enrolment_report(names: list, tournament_name: str) -> str:
    """The same fact in the past tense, for the success notification."""
    if not names:
        return ''
    if len(names) == 1:
        return f'{names[0]} was enrolled in {tournament_name}.'
    listed = ', '.join(names[:-1]) + f' and {names[-1]}'
    return f'{listed} were enrolled in {tournament_name}.'


class BaseMatchDialog:
    """Base class for match dialogs with common functionality."""

    def __init__(self, match: Match = None, on_submit=None):
        self.match = match
        self.on_submit = on_submit
        self.dialog = None
        self._clear_seated = False
        self._clear_started = False
        self._clear_finished = False
        self._clear_confirmed = False
        self._clear_seed = False
        self._initial_updated_at = match.updated_at if match else None
        self.match_service = MatchService()
        self.user_service = UserService()
        self.crew_service = CrewService()
        self.tournament_service = TournamentService()
        self.stream_room_service = StreamRoomService()
        self.bracket_service = BracketService()

    def _get_default_values(self):
        now = now_eastern()
        if self.match:
            return {
                'tournament': self.match.tournament_id if self.match.tournament_id else None,
                'date': format_eastern_date(self.match.scheduled_at) if self.match.scheduled_at else now.strftime('%Y-%m-%d'),
                'time': format_eastern_time(self.match.scheduled_at) if self.match.scheduled_at else now.strftime('%H:%M'),
                'comment': self.match.comment or '',
                'stream_room': self.match.stream_room_id if self.match.stream_room_id else None,
            }
        else:
            return {
                'tournament': None,
                'date': now.strftime('%Y-%m-%d'),
                'time': now.strftime('%H:%M'),
                'comment': '',
                'stream_room': None,
            }

    def _render_tournament_select(self, tournaments, default_value, empty_hint):
        select = ui.select(
            label='Tournament *',
            options={t.id: t.name for t in tournaments},
            value=default_value,
            with_input=True,
        ).props('required').classes('input-full-width')
        if not tournaments:
            # Otherwise a required select with no options opens no menu and
            # answers "Please fill required field(s): Tournament".
            select.disable()
            select.props(f'hint="{empty_hint}"')
        return select

    def _render_date_time_inputs(self, default_date, default_time):
        with ui.row().classes('items-center gap-2'):
            date = native_date_input('Date', default_date, required=True)
            time = native_time_input('Time', default_time, required=True)

        return date, time

    def _render_suggest_time_button(
        self,
        *,
        get_tournament_id: Callable[[], object],
        get_player_ids: Callable[[], list],
        date,
        time,
        missing_message: str,
    ) -> None:
        """Render the 'Suggest a time' button shared by both dialogs.

        The two dialogs source player ids differently (admin from the players
        multi-select, user from the single opponent select plus their own id), so
        the ids are supplied by ``get_player_ids``, evaluated at click time.
        """
        async def suggest_time():
            tournament_id = get_tournament_id()
            player_ids = get_player_ids()
            if not tournament_id or not player_ids:
                with self.dialog:
                    ui.notify(missing_message, color='warning')
                return
            try:
                suggested = await MatchSuggestionService().suggest_match_time(
                    tournament_id=tournament_id,
                    player_ids=player_ids,
                )
                date.value = format_eastern_date(suggested)
                time.value = format_eastern_time(suggested)
                with self.dialog:
                    ui.notify('Suggested time filled in — review and save.', color='info')
            except ValueError as e:
                with self.dialog:
                    ui.notify(str(e), color='warning')

        ui.button('Suggest a time', icon='lightbulb', on_click=suggest_time).props('flat color=secondary').classes('mt-1')

    def _render_clear_buttons(self):
        def make_clear_button(label, icon, attr_flag, match_attr, is_relation=False):
            def clear():
                setattr(self, attr_flag, True)
                btn.disable()
                btn.props('outline')

            if is_relation:
                btn_disabled = getattr(self.match, f'{match_attr}_id', None) is None
            else:
                btn_disabled = getattr(self.match, match_attr) is None

            btn_color = 'gray' if btn_disabled else 'negative'
            btn = ui.button(label, icon=icon, on_click=clear).props(f'outline color={btn_color}').classes('ml-1')
            if btn_disabled:
                btn.disable()
            return btn

        with ui.row().classes('items-center flex-wrap gap-1'):
            make_clear_button('Clear Check In', 'chair', '_clear_seated', 'seated_at')
            make_clear_button('Clear Started', 'play_arrow', '_clear_started', 'started_at')
            make_clear_button('Clear Finish', 'sports_score', '_clear_finished', 'finished_at')
            make_clear_button('Clear Confirmed', 'verified', '_clear_confirmed', 'confirmed_at')
            make_clear_button('Clear Seed', 'casino', '_clear_seed', 'generated_seed', is_relation=True)

    async def _render_watch_switch(self, user):
        if not self.match:
            return
        watcher_service = MatchWatcherService()
        initial_watching = await watcher_service.is_watching(self.match.id, user)
        match_id = self.match.id

        switch_ref = {}

        async def on_change(event, client):
            new_value = bool(event.value)
            try:
                if new_value:
                    await watcher_service.watch(match_id, user)
                    with client:
                        ui.notify(
                            f'Now watching match ID {match_id}. You will receive Discord DMs on updates.',
                            color='positive',
                        )
                else:
                    await watcher_service.unwatch(match_id, user)
                    with client:
                        ui.notify(f'No longer watching match ID {match_id}.', color='positive')
            except ValueError as e:
                switch_ref['widget'].value = not new_value
                switch_ref['widget'].update()
                with client:
                    ui.notify(str(e), color='warning')

        switch_ref['widget'] = ui.switch(
            'Watch this match (Discord DM updates)',
            value=initial_watching,
            on_change=lambda e: background_tasks.create(on_change(e, context.client)),
        )

    def _confirm_delete(self, dialog):
        async def on_confirm():
            await self._delete_match(dialog)
        ConfirmationDialog(
            message="Are you sure you want to delete this match?",
            on_confirm=on_confirm,
            confirm_text="Delete",
            cancel_text="Cancel",
        ).open()

    async def _delete_match(self, dialog):
        try:
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            await self.match_service.delete_match(self.match.id, actor=actor)
            with dialog:
                ui.notify('Match deleted', color='negative')
                dialog.close()
            if self.on_submit:
                await self.on_submit(None)
        except (ValueError, PermissionError) as e:
            with dialog:
                notify_error(e)

    def _confirm_cancel(self, dialog):
        async def on_confirm():
            await self._cancel_match(dialog)
        ConfirmationDialog(
            message=(
                "Cancel this match? Its players and crew will be DMed, and any "
                "open race room will be closed."
            ),
            on_confirm=on_confirm,
            confirm_text="Cancel match",
            cancel_text="Back",
        ).open()

    async def _cancel_match(self, dialog):
        try:
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            await self.match_service.cancel_match(self.match.id, actor=actor)
            with dialog:
                ui.notify('Match cancelled — players and crew notified', color='negative')
                dialog.close()
            if self.on_submit:
                await self.on_submit(None)
        except (ValueError, PermissionError) as e:
            with dialog:
                notify_error(e)

    async def _tournament_name(self, tournament_id) -> str:
        tournament = await self.tournament_service.get_tournament_by_id(tournament_id)
        return tournament.name if tournament else 'this tournament'

    async def _run_submit(
        self,
        dialog,
        *,
        required_fields: dict,
        tournament_id,
        player_ids: list,
        stale_message: str,
        do_update: Callable[[], Awaitable[None]],
        do_create: Callable[[], Awaitable[None]],
        create_success_message: str,
    ) -> None:
        """Shared submit pipeline for both match dialogs.

        Covers the mechanics both ``open()`` submit handlers share: required-field
        validation, ``ensure_players_enrolled``, the optimistic-lock ``updated_at``
        check on edit, and the ``PermissionError``/``ValueError`` handling ladder.
        The dialog-specific service calls are supplied by ``do_update``/``do_create``.

        ``required_fields`` is an ordered ``{label: value}`` mapping; any falsy value
        marks its label as missing.
        """
        missing = [label for label, value in required_fields.items() if not value]
        if missing:
            with self.dialog:
                ui.notify(f'Please fill required field(s): {", ".join(missing)}.', color='warning')
            return

        try:
            newly_enrolled = await self.match_service.ensure_players_enrolled(
                tournament_id, player_ids,
            )
        except ValueError as e:
            with self.dialog:
                notify_error(e)
            return

        if self.match:
            latest_match = await self.match_service.get_match_by_id(self.match.id)
            if latest_match and latest_match.updated_at != self._initial_updated_at:
                with self.dialog:
                    ui.notify(stale_message, color='warning')
                return

            try:
                await do_update()
                with self.dialog:
                    ui.notify('Match updated successfully', color='positive')
                    dialog.close()
                if self.on_submit:
                    await self.on_submit(self.match)
            except (ValueError, PermissionError) as e:
                with self.dialog:
                    notify_error(e)
        else:
            try:
                await do_create()
                with self.dialog:
                    # Say what scheduling the match did besides schedule it.
                    report = enrolment_report(
                        [u.preferred_name for u in newly_enrolled],
                        await self._tournament_name(tournament_id),
                    )
                    ui.notify(
                        f'{create_success_message} — {report}' if report
                        else create_success_message,
                        color='positive',
                    )
                    dialog.close()
                if self.on_submit:
                    await self.on_submit()
            except (ValueError, PermissionError) as e:
                with self.dialog:
                    notify_error(e)

    def _render_submit_footer(self, dialog, submit, *, create_label: str) -> None:
        """Render the shared footer (Delete/Cancel/primary) and wire Enter-to-submit.

        ``create_label`` is the primary-button text used when creating a new match
        ('Create' for admin, 'Submit' for user); editing always shows 'Save'.
        """
        with dialog_actions():
            if self.match:
                ui.button('Delete', on_click=lambda: self._confirm_delete(dialog)).props('color=negative flat')
                # Distinct from the footer's 'Cancel' (which just closes this
                # dialog): calling the match off notifies everyone who committed
                # to it, where Delete is the silent "this shouldn't exist" path.
                ui.button('Cancel match', on_click=lambda: self._confirm_cancel(dialog)).props('color=negative flat')
            ui.space()
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save' if self.match else create_label, on_click=submit).props('color=primary')

        submit_on_enter(dialog, submit)
        dialog.open()

    async def open(self):
        raise NotImplementedError("Subclasses must implement open()")
