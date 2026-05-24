# SGLMan - Claude Development Guide

SGLMan (Speedgaming Live Manager) is a FastAPI + NiceGUI application for managing tournament schedules, matches, users, and crew for speedgaming live events. It integrates with Discord for authentication and user management, uses Tortoise ORM with MySQL, and runs as a single Docker container.

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.115 |
| UI framework | NiceGUI 2.11 |
| ASGI server | Uvicorn |
| ORM | Tortoise ORM 0.24 |
| Migrations | Aerich 0.8 |
| Database | MySQL / MariaDB |
| Auth | Discord OAuth |
| Discord bot | discord.py 2.6 / py-cord |
| Package manager | Poetry |
| Container | Docker + docker-compose |

## Project Structure

```
sglman/
├── main.py                  # FastAPI app entry point; DB init, lifespan, router setup
├── api.py                   # FastAPI API routes (REST endpoints under /api)
├── frontend.py              # Registers NiceGUI pages with FastAPI
├── models.py                # All Tortoise ORM models and Permissions enum
├── start.sh                 # Dev/prod server startup script
├── pyproject.toml           # Poetry config and Aerich settings
├── docker-compose.yml       # Docker service definition
├── Dockerfile               # Container build (python:3.12-slim)
│
├── application/
│   ├── services/            # Business logic layer (MatchService, TournamentService, etc.)
│   ├── repositories/        # Data access layer (MatchRepository, UserRepository, etc.)
│   └── utils/
│       └── timezone.py      # Timezone conversion utilities (Eastern ↔ UTC)
│
├── pages/                   # NiceGUI top-level pages
│   ├── home.py              # Homepage with tabs (schedule, timeline, player dashboard)
│   ├── admin.py             # Admin dashboard with tabs
│   └── home_tabs/           # Sub-tab components for home
│   └── admin_tabs/          # Sub-tab components for admin
│
├── theme/
│   ├── dialog/              # Modal dialogs (match, user, tournament, crew, etc.)
│   ├── tables/              # Reusable table components
│   └── base.py              # Base theme / styling
│
├── middleware/
│   └── auth.py              # Discord OAuth authentication middleware
│
├── migrations/
│   ├── tortoise_config.py   # Tortoise ORM connection config (reads from env vars)
│   └── models/              # Aerich migration files
│
├── presets/                 # Seed generator presets (alttpr/, ootr/, smmap/)
├── discordbot/              # Discord bot integration
└── static/                  # Static assets (CSS, JS, images)
```

## Development Workflows

### Local setup
```bash
poetry install
cp .env.example .env        # fill in DB and Discord credentials
./start.sh dev              # runs on port 8000 with auto-reload
```

### Docker
```bash
docker-compose up           # builds and starts the container on port 8000
```

### Database migrations
```bash
poetry run aerich migrate   # generate a new migration from model changes
poetry run aerich upgrade   # apply pending migrations to the database
```
Migrations run automatically on startup via `main.py:init_db()`.

### API docs
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

## Environment Variables

All loaded from `.env` (automatically by `start.sh` and Docker):

| Variable | Required | Description |
|---|---|---|
| `DB_HOST` | yes | MySQL server hostname |
| `DB_PORT` | yes | MySQL server port |
| `DB_NAME` | yes | Database name |
| `DB_USERNAME` | no | Database user |
| `DB_PASSWORD` | no | Database password |
| `DISCORD_TOKEN` | yes | Discord bot token |
| `STORAGE_SECRET` | yes | NiceGUI storage encryption key |
| `ENVIRONMENT` | no | `dev` or `production` |

## Architecture: Three-Layer Pattern

The codebase follows a strict three-layer separation. **Always respect these boundaries.**

```
Presentation (pages/, theme/)
    ↓ calls
Service Layer (application/services/)
    ↓ calls
Repository Layer (application/repositories/)
    ↓ uses
Models (models.py)
```

### Presentation layer (`pages/`, `theme/`)
- Renders NiceGUI components, handles user interactions
- Calls service methods; never queries the ORM directly for writes
- Catches exceptions from services and shows `ui.notify()`
- Does not contain business logic or validation

### Service layer (`application/services/`)
- Enforces business rules and validation
- Coordinates multiple repository calls
- Writes audit logs via `AuditService`
- Sends Discord notifications
- Raises `ValueError` for user-facing errors; raises exceptions for unexpected failures
- Must not import NiceGUI components

### Repository layer (`application/repositories/`)
- Pure data access: CRUD, ORM queries, `prefetch_related`
- Returns Tortoise model instances
- No business logic, no audit logging, no notifications

### Adding a new feature
1. Add/update model in `models.py` → run `aerich migrate && aerich upgrade`
2. Create or update repository in `application/repositories/`
3. Create or update service in `application/services/`
4. Export from `application/repositories/__init__.py` and `application/services/__init__.py`
5. Create or update UI in `pages/` or `theme/`

## Page Routes

| Route | File | Description |
|---|---|---|
| `/` | `pages/home.py` | Homepage (schedule, timeline, player dashboard) |
| `/schedule` | `pages/home_tabs/schedule.py` | Read-only public schedule |
| `/player` | `pages/home_tabs/player.py` | Player dashboard |
| `/crew` | `pages/crew.py` | Crew (commentator/tracker) signup |
| `/admin` | `pages/admin.py` | Admin dashboard (requires TOURNAMENT_ADMIN+) |
| `/api/*` | `api.py` | REST API endpoints |

### Adding a new page
```python
# 1. Create pages/mypage.py
from nicegui import ui

def create():
    @ui.page('/mypage')
    async def page():
        ...

# 2. Register in frontend.py
import pages.mypage
pages.mypage.create()
```

## Models Overview (`models.py`)

### Permissions enum
```python
class Permissions(IntEnum):
    USER = 0
    TOURNAMENT_ADMIN = 1
    SUPERADMIN = 2
```

### Key models and relationships
- **User** — Discord-authenticated users; `preferred_name` property returns `display_name` or `username`
- **Tournament** — Tournament metadata; has `admins` (ManyToMany with User), `matches`, `players`, `teams`, `announcements`
- **Match** — Core scheduling unit; lifecycle tracked via timestamps (`scheduled_at`, `seated_at`, `started_at`, `finished_at`, `confirmed_at`); `current_state` property returns human-readable state
- **MatchPlayers** — Players in a match; stores `finish_rank` and `assigned_station`
- **TournamentPlayers** — Tournament enrollment
- **StreamRoom** — Named stream stage (Stage 1, Stage 2, etc.)
- **Commentator** / **Tracker** — Crew signups with approval workflow
- **GeneratedSeeds** — Randomizer seed URLs linked to matches
- **SystemConfiguration** — Key-value app settings
- **Announcement** — Tournament announcements
- **AuditLog** — Admin action tracking

### Match lifecycle states
| State | Condition |
|---|---|
| Scheduled | `seated_at` is None |
| Checked In | `seated_at` set, `started_at` None |
| In Progress | `started_at` set, `finished_at` None |
| Finished | `finished_at` set |

## Timezone Handling

**All datetimes are stored in UTC; all user-facing times are in US/Eastern.**

Always use utilities from `application/utils/timezone.py`:

```python
from application.utils.timezone import (
    parse_eastern_datetime,   # user input (date_str, time_str) → UTC datetime
    format_eastern_time,      # UTC datetime → "HH:MM" string
    format_eastern_date,      # UTC datetime → "YYYY-MM-DD" string
    format_eastern_display,   # UTC datetime → "YYYY-MM-DD HH:MM EST"
    now_eastern,              # current time as Eastern-aware datetime
    to_eastern,               # convert any datetime to Eastern
)

# Store: convert user input to UTC
scheduled_at = parse_eastern_datetime("2025-01-15", "14:30")

# Display: convert UTC to Eastern for output
display = format_eastern_display(match.scheduled_at)  # "2025-01-15 14:30 EST"
```

Never store localized datetimes directly; never display raw UTC to users.

## Authentication

Discord OAuth is handled by `middleware/auth.py`. User identity is stored in NiceGUI's `app.storage.user`. Check permissions before any privileged action:

```python
from nicegui import app
from models import Permissions

user_data = app.storage.user.get('user')
if user_data and user_data.get('permission', 0) >= Permissions.TOURNAMENT_ADMIN:
    # allow action
```

## Coding Conventions

- **Async everywhere** — all DB calls and UI handlers must be `async def`
- **Type hints** — use throughout; helps IDE support and documents intent
- **No direct ORM writes in UI** — always go through the service layer
- **Read-only ORM queries from UI are acceptable** for simple display lookups, but prefer repositories
- **Raise `ValueError` for user errors** in services; catch in UI and show `ui.notify(str(e), color='warning')`
- **Audit important actions** — use `AuditService` for creates, updates, deletes
- **No comments explaining what code does** — only add a comment for a non-obvious constraint, workaround, or invariant
- **Keep services stateless** — instantiate per-request or use static methods

## NiceGUI Patterns

NiceGUI ships a comprehensive LLM reference at `nicegui/llms.md` inside the installed package. When working on NiceGUI code, fetch it for the authoritative API surface rather than relying on training data.

### Critical rules (sourced from NiceGUI's official anti-pattern list)

**Never use `asyncio.create_task()` or `asyncio.ensure_future()`** — bare task references can be garbage-collected mid-run and exceptions are silently swallowed. Always use `background_tasks.create()` instead:

```python
# WRONG — task may be GC-cancelled, exceptions vanish silently
asyncio.create_task(my_coroutine())

# CORRECT — NiceGUI keeps the reference and routes exceptions to its handler
from nicegui import background_tasks
background_tasks.create(my_coroutine())
```

This pattern appears everywhere sync event handlers need to call async functions (e.g., `on_click`, `on_change`, keydown handlers, `ui.table.on()`).

**Never block the event loop** — all users share one asyncio loop. Use `async with httpx.AsyncClient()` instead of `requests`, and use `await asyncio.sleep()` not `time.sleep()`.

**Use `@ui.refreshable` for dynamic UI sections** — avoids full page rebuilds:

```python
@ui.refreshable
def match_list():
    for match in current_matches:
        ui.label(match.title)

match_list()  # initial render
# later, after data changes:
match_list.refresh()
```

**Module-level variables are shared across all users** — never store per-user state at module level. Use `app.storage.user` or local variables inside `@ui.page` functions.

### Standard patterns

```python
# Define a page
@ui.page('/example')
async def example_page():
    with ui.card():
        ui.label('Hello')

# Show a dialog
with ui.dialog() as dialog, ui.card():
    ui.label('Confirm?')
    ui.button('Yes', on_click=dialog.close)
dialog.open()

# Notify user
ui.notify('Success', color='positive')   # green
ui.notify('Warning', color='warning')    # yellow
ui.notify('Error',   color='negative')   # red

# Async event from sync handler (e.g. on_change, keydown)
def on_filter_change(*_):
    background_tasks.create(refresh_table())
```

## Discord Integration

The Discord bot starts in `main.py:init_discord_bot()` using `DISCORD_TOKEN`. Bot logic lives in `discordbot/`. Discord OAuth for web auth is handled via `middleware/auth.py` and `application/services/discord_service.py`.

## Refactoring Status

The codebase is mid-refactor toward full three-layer architecture. See `REFACTORING_GUIDE.md` for detailed patterns and examples.

**Completed:**
- `MatchRepository` and `MatchService` — full match CRUD and lifecycle operations

**In progress:**
- Migrating `admin_schedule.py` to use `MatchService`

**Pending:**
- `TournamentRepository` / `TournamentService`
- `UserRepository` / `UserService`
- `CrewRepository` / `CrewService`
- Remaining UI components

When touching any of these areas, prefer completing the refactor to the three-layer pattern rather than adding more direct ORM calls to the UI layer.

## Reference Documents

| File | Purpose |
|---|---|
| `DESIGN.md` | Original requirements and page structure |
| `REFACTORING_GUIDE.md` | Detailed three-layer architecture guide with code examples |
| `TIMEZONE_HANDLING.md` | Datetime/timezone implementation details |
| `migrations/tortoise_config.py` | DB connection configuration |
| `start.sh` | Server startup commands |
| `pyproject.toml` | Dependencies and Aerich config |
| `nicegui/llms.md` (in installed package) | Authoritative NiceGUI API reference for AI assistants — fetch before writing NiceGUI code |
