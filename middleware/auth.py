from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from zenora import APIClient
import os
from typing import Optional
from urllib.parse import parse_qs, urlparse

from nicegui import Client, app, ui
from models import User

# Supporting variables
referrer_path = None

config = {
    "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN"),
    "DISCORD_CLIENT_SECRET": os.getenv("DISCORD_CLIENT_SECRET"),
    "REDIRECT_URL": os.getenv("REDIRECT_URL"),
    "DISCORD_CLIENT_ID": os.getenv("DISCORD_CLIENT_ID"),
    "OAUTH_URL": os.getenv("OAUTH_URL"),
    "STORAGE_SECRET": os.getenv("STORAGE_SECRET")
}

discordClient = APIClient(config["DISCORD_TOKEN"], client_secret=config["DISCORD_CLIENT_SECRET"])

unrestricted_page_routes = {'/login', '/oauth/callback', '/api', '/'}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not app.storage.user.get('authenticated', False):
            if not request.url.path.startswith('/_nicegui') and request.url.path not in unrestricted_page_routes:
                app.storage.user['referrer_path'] = request.url.path
                return RedirectResponse('/login')
        return await call_next(request)

def create() -> None:
    @ui.page('/login')
    def login(client: Client) -> Optional[RedirectResponse]:
        if app.storage.user.get('authenticated', False):
            return RedirectResponse('/')
        with ui.card().classes('absolute-center'):
            with ui.link(target=config["OAUTH_URL"]):
                ui.button('Login with Discord', icon='login')
        return None

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
            if referrer in ['/login', '/oauth/callback']:
                referrer = '/'
            ui.navigate.to(referrer)
            app.storage.user.pop('referrer_path', None)
        except Exception as e:
            print(e)
            ui.notify(f'Error Encountered: {e}')
            ui.navigate.to('/login')