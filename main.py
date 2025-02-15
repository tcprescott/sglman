#!/usr/bin/env python3
import frontend
from fastapi import FastAPI

import api

from nicegui import app, ui

import pages.home

fastapi_app = FastAPI()
fastapi_app.include_router(
    api.router,
    prefix='/api',
    tags=['api'],
)

frontend.init(fastapi_app)
pages.home.create()

if __name__ == '__main__':
    print('Please start the app with the "uvicorn" command as shown in the start.sh script')