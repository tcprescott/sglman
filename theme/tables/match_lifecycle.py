"""Dialog-backed lifecycle callbacks for a ``MatchTableView``.

Presentation-layer glue: opens the shared dialogs, calls the match services,
reports failures through ``notify_error``, and refreshes the row it touched.
The admin Schedule tab and the proctor board both build their view from an
instance of this, so their lifecycle behaviour cannot drift.

Construction is two-phase because the dependency is circular — the view needs
the callbacks, and the callbacks need the view to refresh a row::

    handlers = MatchLifecycleHandlers(page_container, can_crud=can_crud)
    table_view = MatchTableView(columns=..., get_query=..., **handlers.callbacks())
    handlers.table_view = table_view

The read-only ``Match.get(id=..., tenant_id=require_tenant_id())`` loads here are
the sanctioned presentation-layer load-or-404 shape (CLAUDE.md, entry surfaces);
every *write* goes through a service.
"""

from nicegui import app, ui

from application.services import MatchScheduleService, get_user_from_discord_id
from application.tenant_context import require_tenant_id
from models import Match
from theme.dialog import ConfirmationDialog, MatchResultDialog, StationAssignmentDialog
from theme.dialog.match_dialog import AdminMatchDialog
from theme.dialog.stream_room_dialog import StreamRoomDialog
from theme.notify import notify_error


class MatchLifecycleHandlers:
    """The ``on_*`` callbacks a match table needs to run a match's lifecycle."""

    def __init__(self, page_container, *, can_crud: bool):
        self.page_container = page_container
        self.can_crud = can_crud
        self.table_view = None          # assigned by the caller after the view exists
        self.schedule_service = MatchScheduleService()

    def callbacks(self) -> dict:
        """The ``on_*`` kwargs for ``MatchTableView``, gated by ``can_crud``.

        The crud-only three are omitted entirely rather than passed as ``None``:
        ``MatchTableView`` keys its slot registration off callback presence, so
        omission is what hides the control.
        """
        cb = {
            'on_generate_seed': self.on_generate_seed,
            'on_seat': self.on_seat,
            'on_start': self.on_start,
            'on_finish': self.on_finish,
            'on_assign_stations': self.on_assign_stations,
        }
        if self.can_crud:
            cb['on_edit'] = self.on_edit
            cb['on_confirm'] = self.on_confirm
            cb['on_edit_result'] = self.on_edit_result
            cb['on_edit_stream_room'] = self.on_edit_stream_room
        return cb

    async def _actor(self):
        return await get_user_from_discord_id(app.storage.user.get('discord_id'))

    async def on_edit(self, match_id: int):
        match = await Match.get(id=match_id, tenant_id=require_tenant_id())

        async def after_edit(_):
            await self.table_view.update_row_by_id(match_id)
        with self.page_container:
            dialog = AdminMatchDialog(match=match, on_submit=after_edit)
            await dialog.open()

    async def on_generate_seed(self, match_id: int):
        actor = await self._actor()
        success, message, _ = await self.schedule_service.generate_seed(match_id, actor=actor)

        with self.page_container:
            if success:
                ui.notify(message, color='positive')
            else:
                # Check if it's just "already in progress" (not an error per se)
                if "already in progress" in message.lower():
                    pass  # Skip notification, just refresh
                else:
                    ui.notify(message, color='warning' if "already been generated" in message else 'negative')

        # Always refresh the row to clear spinner
        await self.table_view.update_row_by_id(match_id)

    async def on_seat(self, match_id: int):
        match = await Match.get(id=match_id, tenant_id=require_tenant_id()).prefetch_related('players', 'players__user')

        async def handle_confirm(_):
            dialog.dialog.close()
            await self.confirm_seating(match)
        with self.page_container:
            dialog = StationAssignmentDialog(
                match=match,
                on_submit=handle_confirm,
                purpose='checkin',
            )
            await dialog.open()

    async def confirm_seating(self, match: Match):
        try:
            actor = await self._actor()
            await self.schedule_service.seat_match(match, actor=actor)
            await self.table_view.update_row_by_id(match.id)
            with self.page_container:
                ui.notify(f'Match #{match.id} checked in.', color='positive')
        except (PermissionError, ValueError) as e:
            with self.page_container:
                notify_error(e)

    async def on_start(self, match_id: int):
        match = await Match.get(id=match_id, tenant_id=require_tenant_id()).prefetch_related('players', 'players__user')
        player_names = ', '.join(
            [p.user.preferred_name for p in match.players])

        async def handle_confirm(_):
            dialog.dialog.close()
            await self.confirm_starting(match)
        with self.page_container:
            dialog = ConfirmationDialog(
                message=f'Start match #{match.id}?\n\n{player_names}',
                confirm_text='Start match',
                tone='primary',
                on_confirm=handle_confirm,
            )
            dialog.open()

    async def confirm_starting(self, match: Match):
        try:
            actor = await self._actor()
            await self.schedule_service.start_match(match, actor=actor)
            await self.table_view.update_row_by_id(match.id)
        except (PermissionError, ValueError) as e:
            with self.page_container:
                notify_error(e)

    async def on_finish(self, match_id: int):
        match = await Match.get(id=match_id, tenant_id=require_tenant_id()).prefetch_related('players', 'players__user')

        async def handle_confirm(_):
            dialog.dialog.close()
            await self.confirm_finishing(match)
        with self.page_container:
            dialog = MatchResultDialog(
                match=match,
                on_submit=handle_confirm
            )
            await dialog.open()

    async def confirm_finishing(self, match: Match):
        try:
            actor = await self._actor()
            await self.schedule_service.finish_match(match, actor=actor)
            await self.table_view.update_row_by_id(match.id)
        except (PermissionError, ValueError) as e:
            with self.page_container:
                notify_error(e)

    async def on_confirm(self, match_id: int):
        match = await Match.get(id=match_id, tenant_id=require_tenant_id()).prefetch_related('players', 'players__user')
        player_names = ', '.join(
            [p.user.preferred_name for p in match.players])

        async def handle_confirm(_):
            dialog.dialog.close()
            await self.confirm_confirming(match)
        with self.page_container:
            dialog = ConfirmationDialog(
                message=f'Confirm the recorded result for match #{match.id}?\n\n{player_names}',
                confirm_text='Confirm result',
                tone='primary',
                on_confirm=handle_confirm,
            )
            dialog.open()

    async def confirm_confirming(self, match: Match):
        try:
            actor = await self._actor()
            await self.schedule_service.confirm_match(match, actor=actor)
            await self.table_view.update_row_by_id(match.id)
        except (PermissionError, ValueError) as e:
            with self.page_container:
                notify_error(e)

    async def on_edit_result(self, match_id: int):
        """Correct the winner already recorded on a finished match.

        Deliberately has no ``finish_match`` step: the match is already
        finished, and re-finishing it would rewrite ``finished_at`` and fire a
        second round of notifications for a match nobody just played. Recording
        the result is the whole of the change. A settled bracket game is
        refused by the service, which is the one correction path that
        re-advances the bracket.
        """
        match = await Match.get(
            id=match_id, tenant_id=require_tenant_id(),
        ).prefetch_related('players', 'players__user')

        async def after_edit(_):
            await self.table_view.update_row_by_id(match_id)

        with self.page_container:
            dialog = MatchResultDialog(match=match, on_submit=after_edit, mode='edit')
            await dialog.open()

    async def on_edit_stream_room(self, match_id: int):
        match = await Match.get(id=match_id, tenant_id=require_tenant_id())

        async def after_edit(_):
            await self.table_view.update_row_by_id(match_id)
        with self.page_container:
            dialog = StreamRoomDialog(match=match, on_submit=after_edit)
            await dialog.open()

    async def on_assign_stations(self, match_id: int):
        match = await Match.get(id=match_id, tenant_id=require_tenant_id()).prefetch_related('tournament', 'players', 'players__user')

        async def after_assign(_):
            await self.table_view.update_row_by_id(match_id)
        with self.page_container:
            dialog = StationAssignmentDialog(match=match, on_submit=after_assign, purpose='stations')
            await dialog.open()
