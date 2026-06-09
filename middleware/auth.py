import functools
import os
import re
from typing import Iterable, Optional
from urllib.parse import parse_qs, quote, urlparse

from fastapi import Request
from nicegui import Client, app, ui
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from zenora import APIClient

from application.services.auth_service import AuthService, current_user_from_storage
from application.utils.mock_discord import is_mock_discord
from models import Role, User

# Supporting variables
referrer_path = None

_base_url = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
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

# Registry of routes that require authentication; populated by protected_page decorator.
# Plain strings match exactly; entries containing ``{param}`` placeholders are
# compiled to regexes so dynamic NiceGUI routes match incoming request paths.
protected_routes: set[str] = set()


def _matches_protected_route(path: str) -> bool:
    for route in protected_routes:
        if '{' in route:
            pattern = '^' + re.sub(r'\{[^/}]+\}', r'[^/]+', route) + '$'
            if re.match(pattern, path):
                return True
        elif path == route:
            return True
    return False

def protected_page(
    path: str,
    *,
    roles: Optional[Iterable[Role]] = None,
    allow_tournament_membership: bool = False,
    **page_kwargs,
):
    """Register a NiceGUI page that requires authentication and optional roles.

    Args:
        path: Page route.
        roles: If set, the user must hold at least one of these global roles.
        allow_tournament_membership: If True, users who are a Tournament Admin
            or Crew Coordinator of any tournament also pass the role gate.
            Use for pages whose subset of features may be available to per-
            tournament admins (e.g. the admin dashboard shell).
    """
    role_list = list(roles) if roles else None

    def decorator(func):
        protected_routes.add(path)

        if role_list is None and not allow_tournament_membership:
            return ui.page(path, **page_kwargs)(func)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            user = await current_user_from_storage()
            allowed = False
            if user is not None and role_list:
                held = await AuthService.get_roles(user)
                allowed = bool(held.intersection(role_list))
            if not allowed and allow_tournament_membership:
                allowed = await AuthService.can_view_admin(user)
            if not allowed:
                from theme.base import BaseLayout
                await BaseLayout(page_name='denied').render()
                ui.label('You do not have permission to view this page.').classes('text-error')
                return
            return await func(*args, **kwargs)

        return ui.page(path, **page_kwargs)(wrapper)
    return decorator

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Enforce authentication only for routes that were explicitly marked protected
        if not app.storage.user.get('authenticated', False):
            path = request.url.path
            if not path.startswith('/_nicegui') and _matches_protected_route(path):
                app.storage.user['referrer_path'] = path
                return RedirectResponse('/login')
        return await call_next(request)

def create() -> None:
    if is_mock_discord():
        from middleware import mock_auth
        mock_auth.create()
        return

    @ui.page('/login')
    def login(client: Client) -> Optional[RedirectResponse]:
        if app.storage.user.get('authenticated', False):
            return RedirectResponse('/')
        return RedirectResponse(config["OAUTH_URL"])

    @ui.page('/logout')
    def logout(client: Client) -> Optional[RedirectResponse]:
        app.storage.user.clear()
        return RedirectResponse('/')

    @ui.page('/oauth/callback')
    async def oauth_callback(client: Client):
        await client.connected()
        url = await ui.run_javascript('window.location.href')
        try:
            parsed_url = urlparse(url)
            code = parse_qs(parsed_url.query)['code'][0]
            access_token = discordClient.oauth.get_access_token(code, config["REDIRECT_URL"]).access_token
            bearer_client = APIClient(access_token, bearer=True)
            current_user = bearer_client.users.get_current_user()

            app.storage.user.update({
                'username': current_user.username,
                'avatar': current_user.avatar_url,
                'authenticated': True,
                'discord_id': current_user.id
            })

            user, created = await User.get_or_create(discord_id=current_user.id, defaults={
                'username': current_user.username,
                'access_token': access_token
            })
            if not created:
                user.username = current_user.username
                user.access_token = access_token
                await user.save()

            referrer = app.storage.user.get('referrer_path', '/')
            # Avoid redirecting to login/callback
            if referrer in ['/login', '/logout', '/oauth/callback']:
                referrer = '/'
            ui.navigate.to(referrer)
            app.storage.user.pop('referrer_path', None)
        except Exception as e:
            print(e)
            ui.notify(f'Error Encountered: {e}')
            ui.navigate.to('/login')