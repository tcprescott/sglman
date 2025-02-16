from fastapi import FastAPI

from nicegui import app, ui

from pages import home, test

def init(fastapi_app: FastAPI) -> None:
    home.create()
    test.create()
    ui.run_with(
        fastapi_app,
        # mount_path='/gui',  # NOTE this can be omitted if you want the paths passed to @ui.page to be at the root
        storage_secret='pick your private secret here',  # NOTE setting a secret is optional but allows for persistent storage per user
    )