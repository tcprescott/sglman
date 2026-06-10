#!/usr/bin/env python3
"""Main entry point for the SGL On Site FastAPI application.

Initializes the database, sets up API and frontend routes, and manages application lifespan.
"""

# import api
from contextlib import asynccontextmanager
import os
from typing import AsyncGenerator

from application.services.discord_service import get_discord_bot
from application.services import discord_queue
from application.utils.easter_eggs import random_fact
from application.utils.mock_discord import is_mock_discord
import asyncio
from aerich import Command
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from tortoise import Tortoise

import frontend
import api
from migrations.tortoise_config import TORTOISE_ORM


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

async def init_discord_bot() -> None:
    """
    Initialize the Discord bot.
    """
    if is_mock_discord():
        print('MOCK_DISCORD enabled — skipping Discord bot start.')
        return
    token = os.environ.get('DISCORD_TOKEN')
    bot = get_discord_bot()
    if token:
        loop = asyncio.get_event_loop()
        loop.create_task(bot.start(token))
    else:
        print('Warning: DISCORD_TOKEN not set. Discord features will not work.')

async def close_discord_bot() -> None:
    """
    Close the Discord bot connection.
    """
    if is_mock_discord():
        return
    bot = get_discord_bot()
    await bot.close()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Context manager for FastAPI lifespan events.
    Initializes and tears down the database and Discord bot on application startup and shutdown.
    """
    await init_db()
    await init_discord_bot()
    discord_queue.start()
    yield
    await discord_queue.stop()
    await close_discord_bot()
    await close_db()

# Create FastAPI app with metadata for API documentation
app: FastAPI = FastAPI(
    title="SGL On Site API",
    description="API for managing tournaments, matches, players, commentators, and trackers for SGL On Site events",
    version="1.0.0",
    lifespan=lifespan,
    # By default, API docs are accessible at /docs (Swagger) and /redoc (ReDoc)
    docs_url="/api/docs",  # Customize the Swagger UI URL
    redoc_url="/api/redoc",  # Customize the ReDoc URL
)

class FunFactMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers['X-Fun-Fact'] = random_fact()
        return response

app.add_middleware(FunFactMiddleware)

app.include_router(
    api.router,
    prefix='/api',
    tags=['api'],
)

frontend.init(app)

if __name__ == '__main__':
    print('Please start the app with the "uvicorn" command as shown in the start.sh script')