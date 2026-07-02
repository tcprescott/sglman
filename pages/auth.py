"""Authentication page routes: Discord OAuth ``/login``, ``/logout`` and
``/oauth/callback``.

This is the presentation half of authentication — it only registers the
``@ui.page`` routes. The actual middleware (``AuthMiddleware``, the
``protected_page`` decorator and the protected-route registry) lives in
``middleware/auth.py``.

When ``MOCK_DISCORD`` is enabled the three routes are replaced by a local
user-picker so developers can impersonate any user (or mint a new one) without
performing real Discord OAuth. User provisioning writes go through
``UserService`` to keep the presentation layer free of direct ORM writes.
"""

import logging
import os
import random
import secrets
from typing import Optional
from urllib.parse import parse_qs, quote, urlparse

from nicegui import Client, app, ui
from starlette.responses import RedirectResponse
from zenora import APIClient

from application.services import UserService
from application.services.discord_role_mapping_service import DiscordRoleMappingService
from application.utils.environment import get_base_url
from application.utils.mock_discord import is_mock_discord
from models import Role, User

logger = logging.getLogger(__name__)

_base_url = get_base_url()
_client_id = os.getenv("DISCORD_CLIENT_ID")
_redirect_url = os.getenv("REDIRECT_URL") or f"{_base_url}/oauth/callback"

config = {
    "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN"),
    "DISCORD_CLIENT_SECRET": os.getenv("DISCORD_CLIENT_SECRET"),
    "REDIRECT_URL": _redirect_url,
    "DISCORD_CLIENT_ID": _client_id,
    "OAUTH_URL": os.getenv("OAUTH_URL") or (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={_client_id}"
        f"&redirect_uri={quote(_redirect_url, safe='')}"
        f"&response_type=code"
        f"&scope=identify"
    ),
    "STORAGE_SECRET": os.getenv("STORAGE_SECRET")
}

discordClient = (
    APIClient(config["DISCORD_TOKEN"], client_secret=config["DISCORD_CLIENT_SECRET"])
    if not is_mock_discord() else None
)


def create() -> None:
    if is_mock_discord():
        _create_mock()
        return

    @ui.page('/login')
    def login(client: Client) -> Optional[RedirectResponse]:
        if app.storage.user.get('authenticated', False):
            return RedirectResponse('/')
        # CSRF protection: bind this login attempt to a one-time state token
        # that must come back on the OAuth callback.
        state = secrets.token_urlsafe(32)
        app.storage.user['oauth_state'] = state
        sep = '&' if '?' in config["OAUTH_URL"] else '?'
        return RedirectResponse(f'{config["OAUTH_URL"]}{sep}state={quote(state, safe="")}')

    @ui.page('/logout')
    def logout(client: Client) -> Optional[RedirectResponse]:
        app.storage.user.clear()
        return RedirectResponse('/')

    @ui.page('/oauth/callback')
    async def oauth_callback(client: Client):
        await client.connected()
        url = await ui.run_javascript('window.location.href')
        expected_state = app.storage.user.pop('oauth_state', None)
        try:
            parsed_url = urlparse(url)
            params = parse_qs(parsed_url.query)

            if 'error' in params:
                logger.warning('OAuth callback returned error: %s', params.get('error'))
                ui.notify('Discord login was cancelled or denied.', color='warning')
                ui.navigate.to('/login')
                return

            returned_state = (params.get('state') or [None])[0]
            if not expected_state or returned_state != expected_state:
                logger.warning('OAuth state mismatch on callback.')
                ui.notify('Login session expired or invalid. Please try again.', color='warning')
                ui.navigate.to('/login')
                return

            code = (params.get('code') or [None])[0]
            if not code:
                logger.warning('OAuth callback missing authorization code.')
                ui.notify('Login failed. Please try again.', color='warning')
                ui.navigate.to('/login')
                return

            access_token = discordClient.oauth.get_access_token(code, config["REDIRECT_URL"]).access_token
            bearer_client = APIClient(access_token, bearer=True)
            current_user = bearer_client.users.get_current_user()

            user, _created = await UserService().provision_from_discord_login(
                current_user.id, current_user.username,
            )

            # Deactivated accounts cannot log in (mirrors the REST API's
            # is_active rejection in api/dependencies.py).
            if not user.is_active:
                logger.warning('Inactive account %s attempted web login', current_user.id)
                app.storage.user.clear()
                ui.notify(
                    'This account is inactive. Contact staff if you believe this is a mistake.',
                    color='negative',
                )
                ui.navigate.to('/login')
                return

            app.storage.user.update({
                'username': current_user.username,
                'avatar': current_user.avatar_url,
                'authenticated': True,
                'discord_id': current_user.id
            })

            # Map the user's Discord guild roles onto application roles.
            # Self-defensive: never raises, so login is never blocked.
            await DiscordRoleMappingService().sync_user_roles(user)

            referrer = app.storage.user.get('referrer_path', '/')
            # Avoid redirecting to login/callback
            if referrer in ['/login', '/logout', '/oauth/callback']:
                referrer = '/'
            ui.navigate.to(referrer)
            app.storage.user.pop('referrer_path', None)
        except Exception:
            logger.exception('Unexpected error during OAuth callback')
            ui.notify('An unexpected error occurred during login. Please try again.', color='negative')
            ui.navigate.to('/login')


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


def _create_mock() -> None:
    """Register the MOCK_DISCORD replacements for the three auth routes.

    Turns ``/login`` into a public user-picker that can impersonate any user or
    mint a new one. Never active in production (``is_mock_discord`` refuses it).
    """
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

                users = await User.all().order_by('username').prefetch_related(
                    'roles', 'admin_tournaments', 'crew_coordinated_tournaments',
                )

                def format_roles(u: User) -> str:
                    labels = [r.role.value.replace('_', ' ').title() for r in u.roles]
                    if len(u.admin_tournaments):
                        labels.append(f'TA({len(u.admin_tournaments)})')
                    if len(u.crew_coordinated_tournaments):
                        labels.append(f'CC({len(u.crew_coordinated_tournaments)})')
                    return ', '.join(labels) or '-'

                rows = [
                    {
                        'id': u.id,
                        'username': u.username,
                        'display_name': u.display_name or '',
                        'discord_id': str(u.discord_id),
                        'roles': format_roles(u),
                    }
                    for u in users
                ]
                user_by_id = {u.id: u for u in users}

                columns = [
                    {'name': 'username', 'label': 'Username', 'field': 'username', 'align': 'left', 'sortable': True},
                    {'name': 'display_name', 'label': 'Display Name', 'field': 'display_name', 'align': 'left'},
                    {'name': 'discord_id', 'label': 'Discord ID', 'field': 'discord_id', 'align': 'left'},
                    {'name': 'roles', 'label': 'Roles', 'field': 'roles', 'align': 'left'},
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
                role_options = {r.value: r.name.replace('_', ' ').title() for r in Role}
                role_select = ui.select(
                    options=role_options,
                    value=[],
                    label='Roles',
                    multiple=True,
                ).props('use-chips').classes('w-full')

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
                    user = await UserService().create_mock_login_user(
                        discord_id=discord_id,
                        username=username,
                        display_name=display_name,
                        role_values=role_select.value or [],
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
