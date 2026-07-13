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
from application.services import WebhookService
from application.services import TelemetryService
from application.services import web_push_service
from application.events import event_bus
from application.events import dispatch_queue as event_dispatch_queue
from application.utils.easter_eggs import random_fact
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
    # Importing discordbot registers its interaction handlers and DM view
    # factories with discord_service's registries — the one-way wiring that
    # replaced the old bidirectional import cycle (see
    # docs/reviews/2026-07-project-structure-review.md, roadmap item 21).
    import discordbot  # noqa: F401
    await init_discord_bot()
    # Racetime bot runtime: one long-lived connection per active RacetimeBot
    # category. Gated by RACETIME_BOT_ENABLED (off by default) and mockable via
    # MOCK_RACETIME; a no-op when the switch is off, so it is always safe to call.
    from racetimebot import close_racetime_bot, init_racetime_bot
    await init_racetime_bot()
    # Auto-open worker: opens a racetime room ahead of each eligible scheduled
    # match (opt-in per tournament). Runs only when the racetime runtime is on.
    from application.services import race_room_worker
    from application.utils.environment import racetime_bot_enabled
    if racetime_bot_enabled():
        race_room_worker.start()
    # SpeedGaming ETL sync worker: polls active event links on their cadence and
    # materializes SG episodes into Match rows. Gated by SPEEDGAMING_SYNC_ENABLED
    # (off by default); mockable via MOCK_SPEEDGAMING.
    from application.services import speedgaming_sync_worker
    from application.utils.environment import speedgaming_sync_enabled
    if speedgaming_sync_enabled():
        speedgaming_sync_worker.start()
    # Discord Scheduled Events reconciler: mirrors opted-in tournaments' schedules
    # into each linked guild's Discord events. Gated by DISCORD_EVENTS_SYNC_ENABLED
    # (off by default); uses the mock transport under MOCK_DISCORD.
    from application.services import discord_event_worker
    from application.utils.environment import discord_events_sync_enabled
    if discord_events_sync_enabled():
        discord_event_worker.start()
    discord_queue.start()
    volunteer_reminder.start()
    # Central event bus: start the async-subscriber worker and register the
    # webhook delivery subscriber (fans published events out to staff webhooks).
    event_dispatch_queue.start()
    event_bus.subscribe_async(WebhookService().deliver_event)
    # Engagement telemetry: mirror every published domain event into the
    # TelemetryEvent log (page views / interactions are captured separately from
    # the presentation layer). No event_types filter — record them all.
    event_bus.subscribe_async(TelemetryService().record_event)
    yield
    await race_room_worker.stop()
    await speedgaming_sync_worker.stop()
    await discord_event_worker.stop()
    await close_racetime_bot()
    await volunteer_reminder.stop()
    await event_dispatch_queue.stop()
    await discord_queue.stop()
    await web_push_service.aclose_http_client()
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

app: FastAPI = FastAPI(
    title="SGL On Site API",
    description=API_DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
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
