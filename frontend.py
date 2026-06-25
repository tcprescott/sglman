"""Frontend initialization for the SGL On Site FastAPI application.

Sets up NiceGUI pages and integrates them with the FastAPI app.
"""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from nicegui import app, ui

from application.utils.environment import validate_security_config
from middleware.auth import AuthMiddleware
from middleware.auth import create as auth_create
from middleware.challonge_oauth import create as challonge_oauth_create
from middleware.error_handlers import register_error_handlers
from pages import admin, equipment, home, volunteer

app.add_middleware(AuthMiddleware)


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles subclass that disables caching in development mode."""
    
    def __init__(self, *args, **kwargs):
        self.is_dev = os.environ.get('ENVIRONMENT', 'development') == 'development'
        super().__init__(*args, **kwargs)
    
    async def __call__(self, scope, receive, send):
        if self.is_dev and scope['type'] == 'http':
            # Wrap the send function to add no-cache headers
            async def send_wrapper(message):
                if message['type'] == 'http.response.start':
                    headers = list(message.get('headers', []))
                    # Remove any existing cache-control headers
                    headers = [h for h in headers if h[0].lower() != b'cache-control']
                    # Add no-cache headers
                    headers.append((b'cache-control', b'no-cache, no-store, must-revalidate'))
                    headers.append((b'pragma', b'no-cache'))
                    headers.append((b'expires', b'0'))
                    message['headers'] = headers
                await send(message)
            await super().__call__(scope, receive, send_wrapper)
        else:
            await super().__call__(scope, receive, send)


def init(fastapi_app: FastAPI) -> None:
    """
    Initialize the frontend by registering NiceGUI pages and attaching them to the FastAPI app.

    Args:
        fastapi_app (FastAPI): The FastAPI application instance to integrate with NiceGUI.
    """
    # Refuse to start with an insecure session/DB configuration.
    validate_security_config()

    # Mount static files directory with no-cache in development
    fastapi_app.mount("/static", NoCacheStaticFiles(directory="static"), name="static")

    auth_create()
    challonge_oauth_create()
    admin.create()
    home.create()
    volunteer.create()
    equipment.create()
    ui.run_with(
        fastapi_app,
        # mount_path='/gui',  # NOTE this can be omitted if you want the paths passed to @ui.page to be at the root
        storage_secret=(os.environ.get('STORAGE_SECRET') or '').strip(),  # required; enforced by validate_security_config()
    )
    register_error_handlers(fastapi_app)