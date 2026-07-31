"""Event-handler coroutines for the match table.

``MatchTableView`` mixes this in; the handlers operate on the view's ``self``
(``self.service``, ``self.table``, ``self.update_row_by_id``, the ``on_*``
callbacks, …). ``match.py`` keeps the event *wiring* (``table.on(...)``); the
handler *bodies* live here. Presentation layer: services are reached via the
view's injected instances / lazy imports, never repositories.
"""

from nicegui import app, ui

from application.utils.match_labels import match_row_label
from theme.dialog import ConfirmationDialog, UserDialog
from theme.notify import notify_error


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
                ui.notify(f'You acknowledged {match_row_label(row, with_context=False)}.', color='positive')
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

    async def _handle_toggle_approval(self, role, event):
        from application.services import CrewService, get_user_from_discord_id

        row = event.args['row']
        idx = event.args['idx']
        match_id = row['id']
        match_query = self.get_query()
        prefetch_map = {
            'commentator': ('commentators', 'commentators__user'),
            'tracker': ('trackers', 'trackers__user'),
        }
        attr_map = {
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

        crew_member = items[idx]
        name = crew_member.user.preferred_name
        approving = not crew_member.approved

        async def apply():
            try:
                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                await CrewService().update_crew_approval(
                    crew_member=crew_member,
                    crew_type=role,
                    approved=approving,
                    actor=actor,
                )
                ui.notify(
                    f'{name} {"approved as" if approving else "un-approved as"} {role} '
                    f'for {match_row_label(row, with_context=False)}.',
                    color='positive',
                )
                await self.update_row_by_id(match_id)
            except (ValueError, PermissionError) as e:
                notify_error(e)
            finally:
                dialog.dialog.close()

        if approving:
            message = (f'Approve {name} as {role} for {match_row_label(row)}?\n\n'
                       "They'll get a Discord message asking them to acknowledge the assignment.")
            title, confirm_text, tone = f'Approve {role}', 'Approve', 'primary'
        else:
            message = (f'Remove approval for {name} as {role} for {match_row_label(row)}?\n\n'
                       "This also clears their acknowledgment. They'll get a Discord message "
                       'letting them know.')
            title, confirm_text, tone = f'Un-approve {role}', 'Un-approve', 'negative'

        with self.table_container:
            dialog = ConfirmationDialog(
                message,
                title=title,
                confirm_text=confirm_text,
                cancel_text='Cancel',
                tone=tone,
                on_confirm=apply,
            )
            dialog.open()

    async def _handle_signup_or_undo_role(self, action, role, row):
        """Handle crew signup/undo using service layer."""
        from application.services import CrewService
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
        crew_service = CrewService()

        if action == 'undo':
            # Withdrawing an *approved* commitment is not the same act as
            # dropping one nobody has looked at yet: staff put this person on the
            # match, and the service now tells them it came off. The dialog says
            # so rather than reusing the neutral copy.
            mine = next(
                (c for c in (row.get(f'{role}s') or [])
                 if isinstance(c, dict) and c.get('discord_id') == str(discord_id)),
                None,
            )
            was_approved = bool(mine and mine.get('approved'))

            async def perform_undo():
                try:
                    await crew_service.undo_crew_signup(match_id, user, role)
                    ui.notify(
                        f'You have been removed as a {role} for '
                        f'{match_row_label(row, with_context=False)}.',
                        color='positive',
                    )
                    await self.update_row_by_id(match_id)
                    dialog.dialog.close()
                except ValueError as e:
                    ui.notify(str(e), color='warning')
                    dialog.dialog.close()

            message = f'Remove yourself as a {role} for {match_row_label(row)}?'
            if was_approved:
                message += ('\n\nStaff approved you for this slot — they will be told '
                            'you have withdrawn so they can find cover.')

            dialog = ConfirmationDialog(
                message,
                title=f'Withdraw as {role}',
                confirm_text='Withdraw',
                cancel_text='Cancel',
                tone='negative' if was_approved else 'primary',
                on_confirm=perform_undo,
            )
            dialog.open()

        elif action == 'signup':
            async def update_role_signup():
                try:
                    await crew_service.signup_crew(match_id, user, role)
                    ui.notify(
                        f'Signed up as a {role} for '
                        f'{match_row_label(row, with_context=False)}. Awaiting approval.',
                        color='positive',
                    )
                    await self.update_row_by_id(match_id)
                    dialog.dialog.close()
                except ValueError as e:
                    ui.notify(str(e), color='warning')
                    dialog.dialog.close()

            dialog = ConfirmationDialog(
                f'Sign up as a {role} for {match_row_label(row)}?',
                title=f'Sign up as {role}',
                confirm_text='Sign up',
                cancel_text='Cancel',
                on_confirm=update_role_signup,
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
                ui.notify(
                    f'You acknowledged your {role} assignment for '
                    f'{match_row_label(row, with_context=False)}.',
                    color='positive',
                )
                await self.update_row_by_id(match_id)
            except ValueError as e:
                ui.notify(str(e), color='warning')

    def _handle_open_bracket(self, event):
        """Navigate to the bracket a scheduled game belongs to.

        The row carries the bracket id (``MatchDisplayService._bracket_ref``);
        the bare path lets ``ui.navigate.to`` prepend the tenant's root_path.
        Synchronous — a redirect needs no service call.
        """
        args = getattr(event, 'args', None)
        row = args if isinstance(args, dict) else {}
        bracket = row.get('bracket') if isinstance(row.get('bracket'), dict) else None
        if bracket and bracket.get('id'):
            ui.navigate.to(f"/brackets/{bracket['id']}")

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

    async def _handle_edit_result(self, event):
        match_id = self._event_match_id(event)
        if match_id is not None and self.on_edit_result:
            await self.on_edit_result(match_id)

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
                ui.notify(f'No longer watching {match_row_label(row, with_context=False)}.', color='positive')
            else:
                await self.watcher_service.watch(match_id, user)
                ui.notify(
                    f'Now watching {match_row_label(row, with_context=False)}. '
                    'You will receive Discord DMs on updates.',
                    color='positive',
                )
        except ValueError as e:
            ui.notify(str(e), color='warning')
            return

        idx = next((i for i, r in enumerate(self.table.rows) if r.get('id') == match_id), None)
        if idx is not None:
            self.table.rows[idx]['_watching'] = not currently_watching
            self.table.update()
