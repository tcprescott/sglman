#!/usr/bin/env python3
"""Main entry point for the SGLMan FastAPI application.

Initializes the database, sets up API and frontend routes, and manages application lifespan.
"""

from tortoise import Tortoise
from fastapi import FastAPI
import frontend
import api
from contextlib import asynccontextmanager
from migrations.tortoise_config import TORTOISE_ORM
from aerich import Command
from typing import AsyncGenerator

async def init_db() -> None:
    """
    Initialize the database using Aerich migrations and Tortoise ORM.
    """
    command = Command(tortoise_config=TORTOISE_ORM, app='models', location='./migrations')
    await command.init()
    await command.upgrade()
    await Tortoise.init(config=TORTOISE_ORM)

async def close_db() -> None:
    """
    Close all database connections managed by Tortoise ORM.
    """
    await Tortoise.close_connections()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Context manager for FastAPI lifespan events.
    Initializes and tears down the database on application startup and shutdown.
    """
    await init_db()
    yield
    await close_db()

app: FastAPI = FastAPI(lifespan=lifespan)
app.include_router(
    api.router,
    prefix='/api',
    tags=['api'],
)

frontend.init(app)

if __name__ == '__main__':
    print('Please start the app with the "uvicorn" command as shown in the start.sh script')