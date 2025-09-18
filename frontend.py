"""Frontend initialization for the SGLMan FastAPI application.

Sets up NiceGUI pages and integrates them with the FastAPI app.
"""

from fastapi import FastAPI

from nicegui import app, ui

from pages import home, schedule, player

def init(fastapi_app: FastAPI) -> None:
    """
    Initialize the frontend by registering NiceGUI pages and attaching them to the FastAPI app.

    Args:
        fastapi_app (FastAPI): The FastAPI application instance to integrate with NiceGUI.
    """
    home.create()
    player.create()
    schedule.create()
    # auth.create()
    ui.run_with(
        fastapi_app,
        # mount_path='/gui',  # NOTE this can be omitted if you want the paths passed to @ui.page to be at the root
        storage_secret='pick your private secret here',  # NOTE setting a secret is optional but allows for persistent storage per user
    )