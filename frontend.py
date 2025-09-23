"""Frontend initialization for the SGLMan FastAPI application.

Sets up NiceGUI pages and integrates them with the FastAPI app.
"""

import os
from fastapi import FastAPI

from nicegui import ui, app

from pages import home, admin

from middleware.auth import AuthMiddleware, create as auth_create

app.add_middleware(AuthMiddleware)

def init(fastapi_app: FastAPI) -> None:
    """
    Initialize the frontend by registering NiceGUI pages and attaching them to the FastAPI app.

    Args:
        fastapi_app (FastAPI): The FastAPI application instance to integrate with NiceGUI.
    """
    auth_create()
    admin.create()
    home.create()
    ui.run_with(
        fastapi_app,
        # mount_path='/gui',  # NOTE this can be omitted if you want the paths passed to @ui.page to be at the root
        storage_secret=os.environ.get('STORAGE_SECRET'),  # NOTE setting a secret is optional but allows for persistent storage per user
    )