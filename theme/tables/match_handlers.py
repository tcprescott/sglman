"""Event-handler coroutines for the match table.

``MatchTableView`` mixes this in; the handlers operate on the view's ``self``
(``self.service``, ``self.table``, ``self.update_row_by_id``, the ``on_*``
callbacks, …). ``match.py`` keeps the event *wiring* (``table.on(...)``); the
handler *bodies* live here. Presentation layer: services are reached via the
view's injected instances / lazy imports, never repositories.
"""

from nicegui import app, ui

from theme.dialog import ConfirmationDialog, UserDialog


class MatchTableHandlersMixin:
    """Coroutine handlers for the match-table events, bound to a MatchTableView."""

    # Helper to extract match id from emitted events
    def _event_match_id(self, event):
        if hasattr(event, 'args'):
            args = event.args
            if isinstance(args, dict):
                if 'key' in args:
                    return args['key']
                if 'row' in args and isinstance(args['row'], dict) and 'id' in args['row']:
                    return args['row']['id']
        return None

    async def _handle_acknowledge_match(self, row, client):
        with client:
            discord_id = app.storage.user.get('discord_id', None)
            if not discord_id:
                ui.notify('You must be logged in to acknowledge.', color='warning')
                return
            user = await self.user_service.get_current_user_from_storage(discord_id)
            if not user:
                ui.notify('User not found. Please log in again.', color='warning')
                return
            match_id = row['id']
            try:
                await self.service.acknowledge_match(match_id, user)
                ui.notify(f'You acknowledged match ID {match_id}.', color='positive')
                await self.update_row_by_id(match_id)
            except ValueError as e:
                ui.notify(str(e), color='warning')

    async def _handle_edit_role(self, role, event):
        row = event.args['row']
        idx = event.args['idx']
        match_id = row['id']
        match_query = self.get_query()
        prefetch_map = {
            'player': ('players', 'players__user'),
            'commentator': ('commentators', 'commentators__user'),
            'tracker': ('trackers', 'trackers__user'),
        }
        attr_map = {
            'player': 'players',
            'commentator': 'commentators',
            'tracker': 'trackers',
        }
        if role not in prefetch_map:
            ui.notify(f'Unknown role: {role}', color='warning')
            return
        m = await match_query.filter(id=match_id).prefetch_related(*prefetch_map[role]).first()
        items = getattr(m, attr_map[role], []) if m else []
        if not m or idx >= len(items):
            ui.notify(f'{role.capitalize()} not found.', color='warning')
            return

        user = items[idx].user
        with self.table_container:
            dialog = UserDialog(user)
            await dialog.open()

    async def _handle_approve_role(self, role, event):
        row = event.args['row']
        idx = event.args['idx']
        match_id = row['id']
        match_query = self.get_query()
        prefetch_map = {
            'player': ('players', 'players__user'),
            'commentator': ('commentators', 'commentators__user'),
            'tracker': ('trackers', 'trackers__user'),
        }
        attr_map = {
            'player': 'players',
            'commentator': 'commentators',
            'tracker': 'trackers',
        }
        if role not in prefetch_map:
            ui.notify(f'Unknown role: {role}', color='warning')
            return
        m = await match_query.filter(id=match_id).prefetch_related(*prefetch_map[role]).first()
        items = getattr(m, attr_map[role], []) if m else []
        if not m or idx >= len(items):
            ui.notify(f'{role.capitalize()} not found.', color='warning')
            return
        from theme.dialog import ApproveCrewDialog
        crew_member = items[idx]
        with self.table_container:
            dialog = ApproveCrewDialog(crew_member, role, on_approve=lambda: self.update_row_by_id(match_id))
            await dialog.open()

    async def _handle_signup_or_undo_role(self, action, role, row):
        """Handle crew signup/undo using service layer."""
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            ui.notify(f'You must be logged in to {action}.', color='warning')
            return

        # Get user via service layer
        user = await self.user_service.get_current_user_from_storage(discord_id)
        if not user:
            ui.notify('User not found. Please log in again.', color='warning')
            return

        match_id = row['id']

        if action == 'undo':
            async def perform_undo():
                try:
                    await self.service.undo_crew_signup(match_id, user, role)
                    ui.notify(f'You have been removed as a {role} for match ID {match_id}.', color='positive')
                    await self.update_row_by_id(match_id)
                    dialog.dialog.close()
                except ValueError as e:
                    ui.notify(str(e), color='warning')
                    dialog.dialog.close()

            dialog = ConfirmationDialog(
                f'Are you sure you want to remove yourself as a {role} for match ID {match_id}?',
                confirm_text='Yes',
                cancel_text='No',
                on_confirm=perform_undo
            )
            dialog.open()

        elif action == 'signup':
            async def update_role_signup():
                try:
                    await self.service.signup_crew(match_id, user, role)
                    ui.notify(f'Successfully signed up as a {role} for match ID {match_id}. Awaiting approval.', color='positive')
                    await self.update_row_by_id(match_id)
                    dialog.dialog.close()
                except ValueError as e:
                    ui.notify(str(e), color='warning')
                    dialog.dialog.close()

            dialog = ConfirmationDialog(
                f'Do you want to sign up as a {role} for match ID {match_id}?',
                confirm_text='Yes',
                cancel_text='No',
                on_confirm=update_role_signup
            )
            dialog.open()

    async def _handle_acknowledge_crew(self, role, event, client):
        from application.services import CrewService
        with client:
            row = event.args['row']
            idx = event.args['idx']
            match_id = row['id']
            items = row.get(f'{role}s') or []
            if idx >= len(items) or not isinstance(items[idx], dict) or items[idx].get('id') is None:
                ui.notify('Page is out of date — please refresh and try again.', color='warning')
                return
            crew_id = items[idx]['id']
            discord_id = app.storage.user.get('discord_id', None)
            if not discord_id:
                ui.notify('You must be logged in to acknowledge.', color='warning')
                return
            user = await self.user_service.get_current_user_from_storage(discord_id)
            if not user:
                ui.notify('User not found. Please log in again.', color='warning')
                return
            try:
                await CrewService().acknowledge_crew_assignment(crew_id, role, user)
                ui.notify(f'You acknowledged your {role} assignment for match ID {match_id}.', color='positive')
                await self.update_row_by_id(match_id)
            except ValueError as e:
                ui.notify(str(e), color='warning')

    async def _handle_edit(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_edit:
            await self.on_edit(match_id)

    async def _handle_roll(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_generate_seed:
            await self.on_generate_seed(match_id)

    async def _handle_seat(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_seat:
            await self.on_seat(match_id)

    async def _handle_start(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_start:
            await self.on_start(match_id)

    async def _handle_finish(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_finish:
            await self.on_finish(match_id)

    async def _handle_confirm(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_confirm:
            await self.on_confirm(match_id)

    async def _handle_assign_stations(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_assign_stations:
            await self.on_assign_stations(match_id)

    async def _handle_edit_stream_room(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_edit_stream_room:
            await self.on_edit_stream_room(match_id)

    async def _handle_toggle_watch(self, event):
        row = event.args if isinstance(event.args, dict) else {}
        match_id = row.get('id')
        if match_id is None:
            return

        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            ui.notify('You must be logged in to watch a match.', color='warning')
            return

        user = await self.user_service.get_current_user_from_storage(discord_id)
        if not user:
            ui.notify('User not found. Please log in again.', color='warning')
            return

        currently_watching = bool(row.get('_watching'))
        try:
            if currently_watching:
                await self.watcher_service.unwatch(match_id, user)
                ui.notify(f'No longer watching match ID {match_id}.', color='positive')
            else:
                await self.watcher_service.watch(match_id, user)
                ui.notify(f'Now watching match ID {match_id}. You will receive Discord DMs on updates.', color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
            return

        idx = next((i for i, r in enumerate(self.table.rows) if r.get('id') == match_id), None)
        if idx is not None:
            self.table.rows[idx]['_watching'] = not currently_watching
            self.table.update()
