"""Mock OAuth login flow used when MOCK_DISCORD=true.

Replaces the Discord OAuth redirect with a user picker page so developers can
log in as any existing user, or create a new one with arbitrary fields.
"""

import random
from typing import Optional

from nicegui import Client, app, ui
from starlette.responses import RedirectResponse

from models import Permissions, User


def _login_as(user: User) -> None:
    """Populate app.storage.user the same way the real OAuth callback does."""
    app.storage.user.update({
        'username': user.username,
        'avatar': None,
        'authenticated': True,
        'discord_id': user.discord_id,
    })
    referrer = app.storage.user.get('referrer_path', '/')
    if referrer in ['/login', '/logout', '/oauth/callback']:
        referrer = '/'
    app.storage.user.pop('referrer_path', None)
    ui.navigate.to(referrer)


def create() -> None:
    @ui.page('/login')
    async def mock_login(client: Client):
        if app.storage.user.get('authenticated', False):
            ui.navigate.to('/')
            return

        ui.page_title('Mock Discord Login')

        with ui.column().classes('w-full max-w-4xl mx-auto p-4 gap-4'):
            ui.label('Mock Discord Login').classes('text-2xl font-bold')
            ui.label(
                'MOCK_DISCORD is enabled. Pick an existing user to impersonate, '
                'or create a new one. No real Discord OAuth is performed.'
            ).classes('text-sm text-gray-600')

            with ui.card().classes('w-full'):
                ui.label('Existing users').classes('text-lg font-semibold')

                filter_input = ui.input(label='Filter by username or discord_id').classes('w-full')

                users = await User.all().order_by('username')
                rows = [
                    {
                        'id': u.id,
                        'username': u.username,
                        'display_name': u.display_name or '',
                        'discord_id': str(u.discord_id),
                        'permission': Permissions(u.permission).name,
                    }
                    for u in users
                ]
                user_by_id = {u.id: u for u in users}

                columns = [
                    {'name': 'username', 'label': 'Username', 'field': 'username', 'align': 'left', 'sortable': True},
                    {'name': 'display_name', 'label': 'Display Name', 'field': 'display_name', 'align': 'left'},
                    {'name': 'discord_id', 'label': 'Discord ID', 'field': 'discord_id', 'align': 'left'},
                    {'name': 'permission', 'label': 'Permission', 'field': 'permission', 'align': 'left'},
                    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
                ]

                table = ui.table(columns=columns, rows=rows, row_key='id').classes('w-full')
                table.add_slot('body-cell-actions', '''
                    <q-td :props="props">
                        <q-btn color="primary" dense label="Log in as"
                               @click="$parent.$emit('login_as', props.row)" />
                    </q-td>
                ''')

                def on_login_as(e):
                    user_id = e.args.get('id')
                    user = user_by_id.get(user_id)
                    if user is None:
                        ui.notify('User no longer exists', color='negative')
                        return
                    _login_as(user)

                table.on('login_as', on_login_as)

                def apply_filter(_=None):
                    needle = (filter_input.value or '').lower().strip()
                    if not needle:
                        table.rows = rows
                    else:
                        table.rows = [
                            r for r in rows
                            if needle in r['username'].lower()
                            or needle in r['display_name'].lower()
                            or needle in r['discord_id']
                        ]
                    table.update()

                filter_input.on('update:model-value', apply_filter)

            with ui.card().classes('w-full'):
                ui.label('Create new user').classes('text-lg font-semibold')

                username_input = ui.input(label='Username').classes('w-full')
                display_name_input = ui.input(label='Display name (optional)').classes('w-full')
                discord_id_input = ui.number(
                    label='Discord ID',
                    value=random.randint(10_000_000_000_000_000, 99_999_999_999_999_999),
                    format='%.0f',
                ).classes('w-full')
                permission_select = ui.select(
                    options={p.value: p.name for p in Permissions},
                    value=Permissions.USER.value,
                    label='Permission',
                ).classes('w-full')

                async def create_user():
                    username = (username_input.value or '').strip()
                    if not username:
                        ui.notify('Username is required', color='warning')
                        return
                    try:
                        discord_id = int(discord_id_input.value)
                    except (TypeError, ValueError):
                        ui.notify('Discord ID must be numeric', color='warning')
                        return
                    if await User.exists(discord_id=discord_id):
                        ui.notify('A user with that discord_id already exists', color='warning')
                        return
                    display_name = (display_name_input.value or '').strip() or None
                    user = await User.create(
                        discord_id=discord_id,
                        username=username,
                        display_name=display_name,
                        permission=int(permission_select.value),
                    )
                    ui.notify(f'Created user {user.username} (#{user.discord_id})', color='positive')
                    _login_as(user)

                ui.button('Create and log in', color='green', on_click=create_user)

    @ui.page('/logout')
    def mock_logout(client: Client) -> Optional[RedirectResponse]:
        app.storage.user.clear()
        return RedirectResponse('/')

    @ui.page('/oauth/callback')
    def mock_oauth_callback(client: Client) -> RedirectResponse:
        return RedirectResponse('/')
