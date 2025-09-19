import asyncio
from datetime import datetime

from nicegui import ui

from models import Match, MatchPlayers, StreamRoom, Tournament, User


async def create_match(tournament_id, date_value, time_value, comment_value, player_ids=None):
    match_time = datetime.strptime(
        f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    match = await Match.create(
        tournament_id=tournament_id,
        scheduled_at=match_time
    )
    if player_ids:
        for pid in player_ids:
            user = await User.get(id=pid)
            await MatchPlayers.create(match=match, user=user)
    if comment_value:
        match.comment = comment_value
        await match.save()
    return match


class MatchDialog:
    def __init__(self, match: Match = None, discord_id=None, on_submit=None, select_multiple=False, is_edit=False):
        self.match = match
        self.discord_id = discord_id
        self.on_submit = on_submit
        self.dialog = None
        self.select_multiple = select_multiple
        self.is_edit = is_edit
        self._clear_seated = False
        self._clear_finished = False

    async def open(self):
        users = await User.all().order_by('username')
        tournaments = await Tournament.all().order_by('name')
        stream_rooms = await StreamRoom.all().order_by('name')
        now = datetime.now()
        # Pre-fill values for edit mode
        if self.is_edit and self.match:
            default_tournament = self.match.tournament_id if self.match.tournament_id else None
            default_date = self.match.scheduled_at.strftime(
                '%Y-%m-%d') if self.match.scheduled_at else now.strftime('%Y-%m-%d')
            default_time = self.match.scheduled_at.strftime(
                '%H:%M') if self.match.scheduled_at else now.strftime('%H:%M')
            player_ids = [p.user_id for p in await MatchPlayers.filter(match=self.match)]
            comment_value = self.match.comment or ''
            default_stream_room = self.match.stream_room_id if self.match.stream_room_id else None
        else:
            default_tournament = None
            default_date = now.strftime('%Y-%m-%d')
            default_time = now.strftime('%H:%M')
            player_ids = []
            comment_value = ''
            default_stream_room = None

        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            selected_tournament = ui.select(label='Tournament', options={
                                            t.id: t.name for t in tournaments}, value=default_tournament, with_input=True)
            stream_room_options = {None: '(None)'}
            stream_room_options.update({s.id: s.name for s in stream_rooms})
            selected_stream_room = ui.select(
                label='Stream Room', options=stream_room_options, value=default_stream_room, with_input=True)

            if self.select_multiple or self.is_edit:
                selected_players = ui.select(label='Players', options={
                                             u.id: u.preferred_name for u in users}, value=player_ids, multiple=True, with_input=True)
            else:
                selected_opponent = ui.select(label='Opponent', options={
                                              u.id: u.preferred_name for u in users}, with_input=True)

            with ui.row().classes('justify-between items-center').style('margin-bottom: 1em;'):
                with ui.input('Date (YYYY-MM-DD)', value=default_date) as date:
                    with ui.menu().props('no-parent-event') as menu:
                        with ui.date(value=default_date).bind_value(date):
                            with ui.row().classes('justify-end'):
                                ui.button('Close', on_click=menu.close).props(
                                    'flat')
                    with date.add_slot('append'):
                        ui.icon('edit_calendar').on(
                            'click', menu.open).classes('cursor-pointer')

                with ui.input('Time (24-hour format)', value=default_time) as time:
                    with ui.menu().props('no-parent-event') as menu:
                        with ui.time(value=default_time).bind_value(time):
                            with ui.row().classes('justify-end'):
                                ui.button('Close', on_click=menu.close).props(
                                    'flat')
                    with time.add_slot('append'):
                        ui.icon('access_time').on(
                            'click', menu.open).classes('cursor-pointer')

            comment_input = ui.textarea(label='Comment (optional)', value=comment_value,
                                        placeholder='Add any notes or comments about this match...').style('width: 100%')

            if self.is_edit:
                def make_clear_button(label, attr_flag, match_attr):
                    def clear():
                        setattr(self, attr_flag, True)
                        btn.disable()
                        btn.props('outline color=gray')
                    btn_disabled = getattr(self.match, match_attr) is None
                    btn_color = 'gray' if btn_disabled else 'negative'
                    btn = ui.button(label, on_click=clear).props(
                        f'outline color={btn_color}').style('margin-left: 1em;')
                    if btn_disabled:
                        btn.disable()
                    return btn

                with ui.row().classes('items-center'):
                    make_clear_button(
                        'Clear Seated', '_clear_seated', 'seated_at')
                    make_clear_button(
                        'Clear Finish', '_clear_finished', 'finished_at')

            async def submit():
                tournament_id = selected_tournament.value
                stream_room_id = selected_stream_room.value
                date_value = date.value
                time_value = time.value
                comment_value = comment_input.value
                # Determine player IDs
                if self.select_multiple or self.is_edit:
                    new_player_ids = selected_players.value if isinstance(
                        selected_players.value, list) else [selected_players.value]
                else:
                    opponent_id = selected_opponent.value
                    user = await User.get(discord_id=self.discord_id)
                    new_player_ids = [
                        user.id, opponent_id] if opponent_id else []

                # Validation
                if self.is_edit:
                    if not (new_player_ids and tournament_id and date_value and time_value):
                        with self.dialog:
                            ui.notify('All fields are required.',
                                      color='warning')
                        return
                else:
                    if not (new_player_ids and len(new_player_ids) >= 2 and tournament_id and date_value and time_value):
                        with self.dialog:
                            ui.notify(
                                'Please select at least two players and fill all fields.', color='warning')
                        return

                # Create or update match
                if self.is_edit:
                    match_time = datetime.strptime(
                        f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
                    self.match.tournament_id = tournament_id
                    self.match.stream_room_id = stream_room_id if stream_room_id else None
                    self.match.scheduled_at = match_time
                    self.match.comment = comment_value
                    if hasattr(self, '_clear_seated') and self._clear_seated:
                        self.match.seated_at = None
                    if hasattr(self, '_clear_finished') and self._clear_finished:
                        self.match.finished_at = None
                    await self.match.save()
                    # Update players
                    await MatchPlayers.filter(match=self.match).delete()
                    for pid in new_player_ids:
                        user = await User.get(id=pid)
                        await MatchPlayers.create(match=self.match, user=user)
                    with self.dialog:
                        ui.notify(
                            f'Match updated: Players={new_player_ids}, Date={date_value}, Time={time_value}, Tournament={tournament_id}, StreamRoom={stream_room_id}', color='positive')
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit(self.match)
                else:
                    match = await create_match(
                        tournament_id,
                        date_value,
                        time_value,
                        comment_value,
                        player_ids=new_player_ids
                    )
                    with self.dialog:
                        if self.select_multiple:
                            ui.notify(
                                f'Match submitted: Players={new_player_ids}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                        else:
                            ui.notify(
                                f'Match submitted: Opponent={new_player_ids[1]}, Date={date_value}, Time={time_value}, Tournament={tournament_id}', color='positive')
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit(match)

            async def confirm_delete():
                async def on_confirm():
                    await delete()
                ConfirmationDialog(
                    message="Are you sure you want to delete this match?",
                    on_confirm=on_confirm,
                    confirm_text="Delete",
                    cancel_text="Cancel"
                ).open()

            async def delete():
                await MatchPlayers.filter(match=self.match).delete()
                await self.match.delete()
                with self.dialog:
                    with self.dialog:
                        ui.notify('Match deleted', color='negative')
                        dialog.close()
                if self.on_submit:
                    await self.on_submit(None)

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                if self.is_edit:
                    ui.button('Save', color='green', on_click=submit)
                    ui.button('Delete', color='negative',
                              on_click=confirm_delete)
                else:
                    ui.button('Submit', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            # Allow Enter to submit

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()


class UserEditDialog:
    def __init__(self, user: User = None, on_submit=None):
        self.user = user
        self.on_submit = on_submit
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            username_input = ui.input('Username', value=self.user.username if self.user else '').props(
                'readonly' if self.user else '')
            display_name_input = ui.input(
                'Display Name', value=self.user.display_name if self.user else '')
            is_active_checkbox = ui.checkbox(
                'Active', value=self.user.is_active if self.user else True)
            discord_id_input = ui.input(
                'Discord ID', value=self.user.discord_id if self.user else '') if not self.user else None
            permission_select = ui.select(
                label='Permission',
                options={0: 'User', 1: 'Tournament Admin', 2: 'Superadmin'},
                value=self.user.permission if self.user else 0
            )

            async def submit():
                if self.user:
                    with self.dialog:
                        self.user.display_name = display_name_input.value
                        self.user.is_active = is_active_checkbox.value
                        self.user.permission = permission_select.value
                        await self.user.save()
                        ui.notify('User updated.', color='positive')
                        dialog.close()
                        if self.on_submit:
                            await self.on_submit(self.user)
                else:
                    # Create new user
                    username = username_input.value.strip()
                    display_name = display_name_input.value.strip()
                    is_active = is_active_checkbox.value
                    permission = permission_select.value
                    discord_id = discord_id_input.value if discord_id_input else None

                    if not username:
                        with self.dialog:
                            ui.notify('Username is required.', color='warning')
                        return
                    new_user = await User.create(
                        username=username,
                        display_name=display_name,
                        is_active=is_active,
                        permission=permission,
                        discord_id=discord_id
                    )
                    with self.dialog:
                        ui.notify('User created.', color='positive')
                        dialog.close()
                        if self.on_submit:
                            await self.on_submit(new_user)

            async def open_message_dialog():
                if self.user:
                    dialog_instance = SendMessageDialog(self.user)
                    await dialog_instance.open()

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                if self.user:
                    ui.button('Save', color='green', on_click=submit)
                    ui.button('Send Message', color='primary',
                              on_click=open_message_dialog)
                else:
                    ui.button('Create', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            # Allow Enter to submit

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()


class TournamentEditDialog:
    def __init__(self, tournament=None, on_submit=None):
        self.tournament = tournament
        self.on_submit = on_submit
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            name_input = ui.input(
                'Tournament Name', value=self.tournament.name if self.tournament else '')
            description_input = ui.textarea(
                'Description', value=self.tournament.description if self.tournament and self.tournament.description else '').style('width: 100')
            seed_generator_input = ui.input(
                'Seed Generator', value=self.tournament.seed_generator if self.tournament and self.tournament.seed_generator else '')
            with ui.row():
                players_per_match_input = ui.number(
                    'Players per Match', value=self.tournament.players_per_match if self.tournament else 2, min=1, max=100)
                team_size_input = ui.number(
                    'Team Size', value=self.tournament.team_size if self.tournament else 1, min=1, max=100)
            staff_administered_checkbox = ui.checkbox(
                'Staff Administered', value=self.tournament.staff_administered if self.tournament else False)
            is_active_checkbox = ui.checkbox(
                'Active', value=self.tournament.is_active if self.tournament else True)

            async def submit():
                if self.tournament:
                    with self.dialog:
                        self.tournament.name = name_input.value
                        self.tournament.description = description_input.value
                        self.tournament.seed_generator = seed_generator_input.value
                        self.tournament.is_active = is_active_checkbox.value
                        self.tournament.players_per_match = players_per_match_input.value
                        self.tournament.team_size = team_size_input.value
                        self.tournament.staff_administered = staff_administered_checkbox.value
                        await self.tournament.save()
                        ui.notify('Tournament updated.', color='positive')
                        dialog.close()
                        if self.on_submit:
                            await self.on_submit(self.tournament)
                else:
                    name = name_input.value.strip()
                    description = description_input.value.strip()
                    seed_generator = seed_generator_input.value.strip()
                    is_active = is_active_checkbox.value
                    players_per_match = players_per_match_input.value
                    team_size = team_size_input.value
                    staff_administered = staff_administered_checkbox.value
                    if not name:
                        with self.dialog:
                            ui.notify('Tournament name is required.',
                                      color='warning')
                        return
                    new_tournament = await Tournament.create(
                        name=name,
                        description=description,
                        seed_generator=seed_generator,
                        is_active=is_active,
                        players_per_match=players_per_match,
                        team_size=team_size,
                        staff_administered=staff_administered
                    )
                    with self.dialog:
                        ui.notify('Tournament created.', color='positive')
                        dialog.close()
                        if self.on_submit:
                            await self.on_submit(new_tournament)

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                if self.tournament:
                    ui.button('Save', color='green', on_click=submit)
                else:
                    ui.button('Create', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            # Allow Enter to submit

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()


class SendMessageDialog:
    def __init__(self, user, send_callback=None):
        self.user = user
        self.send_callback = send_callback if send_callback else self.send_message
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            message_input = ui.textarea(
                label='Message', placeholder='Enter message to send...').style('width: 100%')

            async def send_message():
                with self.dialog:
                    await self.send_callback(self.user, message_input.value)
                    with self.dialog:
                        await self.send_callback(self.user, message_input.value)
                        ui.notify('Message sent.', color='positive')
                        dialog.close()
            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                ui.button('Send', color='green', on_click=send_message)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            # Allow Enter to submit

            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(send_message())
            dialog.on('keydown', on_keydown)
            dialog.open()

    async def send_message(self, user, message):
        # Implement your message sending logic here
        print(f"Send message to {user.username} ({user.id}): {message}")


class ConfirmationDialog:
    def __init__(self, message: str = "Are you sure?", on_confirm=None, confirm_text="Confirm", cancel_text="Cancel"):
        self.message = message
        self.on_confirm = on_confirm
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.dialog = None

    def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            ui.label(self.message).style(
                'font-size: 1.1em; margin-bottom: 1em;')
            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                if self.on_confirm:
                    ui.button(self.confirm_text, color='negative',
                              on_click=self.on_confirm)
                else:
                    ui.button(self.confirm_text, color='negative',
                              on_click=dialog.close)
                ui.button(self.cancel_text, color='gray',
                          on_click=dialog.close)
        dialog.open()
