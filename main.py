#!/usr/bin/env python3
"""Main entry point for the SGL On Site FastAPI application.

Initializes the database, sets up API and frontend routes, and manages application lifespan.
"""

# import api
from contextlib import asynccontextmanager
import logging
import os
from typing import AsyncGenerator, Optional

from application.services.discord_service import get_discord_bot
from application.services import discord_queue
from application.services import volunteer_reminder
from application.utils.easter_eggs import random_fact
from application.utils.environment import is_production
from application.utils.mock_discord import is_mock_discord
from application.utils.sentry import init_sentry
import asyncio
from aerich import Command
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from tortoise import Tortoise

import frontend
import api
from middleware.security_headers import SecurityHeadersMiddleware
from migrations.tortoise_config import TORTOISE_ORM

# Configure application logging once, at import of the entrypoint. Without this
# app loggers fall through to Python's lastResort handler: INFO is dropped and
# WARNING+ has no timestamps. basicConfig is a no-op if handlers already exist.
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger('sglman.main')

# Reference to the Discord bot's background task, kept so it is not garbage
# collected and so shutdown can cancel it cleanly.
_bot_task: Optional[asyncio.Task] = None


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

def _log_bot_task_result(task: asyncio.Task) -> None:
    """Surface a bot startup/gateway failure immediately instead of letting it
    sit unobserved in a GC-able task (bad token, intents, gateway crash)."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error('Discord bot task exited with an exception', exc_info=exc)


async def init_discord_bot() -> None:
    """
    Initialize the Discord bot.
    """
    global _bot_task
    if is_mock_discord():
        logger.info('MOCK_DISCORD enabled — skipping Discord bot start.')
        return
    token = os.environ.get('DISCORD_TOKEN')
    bot = get_discord_bot()
    if token:
        _bot_task = asyncio.create_task(bot.start(token))
        _bot_task.add_done_callback(_log_bot_task_result)
    else:
        logger.warning('DISCORD_TOKEN not set. Discord features will not work.')

async def close_discord_bot() -> None:
    """
    Close the Discord bot connection.
    """
    global _bot_task
    if is_mock_discord():
        return
    bot = get_discord_bot()
    await bot.close()
    if _bot_task is not None:
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception('Discord bot task errored during shutdown')
        _bot_task = None

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Context manager for FastAPI lifespan events.
    Initializes and tears down the database and Discord bot on application startup and shutdown.
    """
    await init_db()
    await init_discord_bot()
    discord_queue.start()
    volunteer_reminder.start()
    yield
    await volunteer_reminder.stop()
    await discord_queue.stop()
    await close_discord_bot()
    await close_db()

# Create FastAPI app with metadata for API documentation
API_DESCRIPTION = """
REST API for managing tournaments, matches, players, crew, and event
operations for SGL On Site.

## Authentication

Every endpoint requires a **personal API token**. Generate one on your
profile page (Edit Your Information -> API Tokens), then send it as a bearer
token:

    Authorization: Bearer sglman_pat_xxxxxxxx...

A token acts with the exact permissions and scope of the user who created it --
the same role checks that gate the web UI apply here. A token marked
**read-only** can call read (GET) endpoints only.

Click **Authorize** and paste your token to try the endpoints below.
"""

# Initialize Sentry before the app/middleware are constructed so its
# instrumentation wraps the request path. No-op when SENTRY_DSN is unset.
init_sentry()

# Expose interactive API docs only outside production to avoid publishing the
# full endpoint surface; in production these URLs return 404.
_docs_enabled = not is_production()

app: FastAPI = FastAPI(
    title="SGL On Site API",
    description=API_DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if _docs_enabled else None,
    redoc_url="/api/redoc" if _docs_enabled else None,
    openapi_url="/api/openapi.json" if _docs_enabled else None,
)

_HEADER_TRANS = str.maketrans({
    '–': '-',   # en-dash
    '—': '-',   # em-dash
    '‘': "'",   # left single quote
    '’': "'",   # right single quote
    '“': '"',   # left double quote
    '”': '"',   # right double quote
    '·': '.',   # middle dot
})


class FunFactMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers['X-Fun-Fact'] = random_fact().translate(_HEADER_TRANS)
        return response

app.add_middleware(FunFactMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(
    api.router,
    prefix='/api',
)

frontend.init(app)

if __name__ == '__main__':
    print('Please start the app with the "uvicorn" command as shown in the start.sh script')