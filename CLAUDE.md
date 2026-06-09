# SGLMan - Claude Development Guide

SGLMan (Speedgaming Live Manager) is a FastAPI + NiceGUI application for managing tournament schedules, matches, users, and crew for speedgaming live events. It integrates with Discord for authentication and user management, uses Tortoise ORM with PostgreSQL, and runs as a single Docker container.

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.115 |
| UI framework | NiceGUI 2.11 |
| ASGI server | Uvicorn |
| ORM | Tortoise ORM 0.24 |
| Migrations | Aerich 0.8 |
| Database | PostgreSQL |
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
│   ├── home.py              # Homepage with tabs (schedule, on-air, profile, player)
│   ├── admin.py             # Admin dashboard with tabs
│   ├── triforce_texts.py    # Player triforce text submission (per-tournament)
│   ├── home_tabs/           # Sub-tab components for home
│   └── admin_tabs/          # Sub-tab components for admin (reports/ is a sub-package)
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
| `DB_HOST` | yes | PostgreSQL server hostname |
| `DB_PORT` | yes | PostgreSQL server port (default 5432) |
| `DB_NAME` | yes | Database name |
| `DB_USERNAME` | no | Database user |
| `DB_PASSWORD` | no | Database password |
| `DISCORD_TOKEN` | yes | Discord bot token |
| `STORAGE_SECRET` | yes | NiceGUI storage encryption key |
| `ENVIRONMENT` | no | `dev` or `production` |
| `MOCK_DISCORD` | no | When `true`, bypasses Discord OAuth (renders a user picker at `/login`) and stubs all `DiscordService` calls. Use for local development without a real Discord app. |

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
| `/` | `pages/home.py` | Homepage (tabs: Schedule / On Air / Profile / Player) |
| `/triforcetexts/{tournament_id}` | `pages/triforce_texts.py` | Player triforce text submission (requires login) |
| `/admin` | `pages/admin.py` | Admin dashboard — tabs vary by role (requires login + any admin role) |
| `/login` | `middleware/auth.py` | Discord OAuth redirect |
| `/logout` | `middleware/auth.py` | Clears session |
| `/oauth/callback` | `middleware/auth.py` | OAuth return handler |
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

### Role enum
```python
class Role(str, Enum):
    STAFF = 'staff'
    PROCTOR = 'proctor'
    STREAM_MANAGER = 'stream_manager'
```

Roles are stored in the `UserRole` junction table (many-to-many). A user may hold multiple roles.

### Key models and relationships
- **User** — Discord-authenticated users; `preferred_name` returns `display_name` or `username`
- **UserRole** — Maps users to `Role` values; records who granted the role
- **UserTeams** / **Team** — Team membership within a tournament
- **Tournament** — Tournament metadata; has `admins` and `crew_coordinators` (both ManyToMany with User), `matches`, `players`, `teams`, `announcements`
- **Match** — Core scheduling unit; lifecycle tracked via timestamps (`scheduled_at`, `seated_at`, `started_at`, `finished_at`, `confirmed_at`); `current_state` property returns human-readable state
- **MatchPlayers** — Players in a match; stores `finish_rank` and `assigned_station`
- **MatchAcknowledgment** — Tracks whether each player has acknowledged a match
- **MatchWatcher** — Users who are watching a match for notifications
- **TournamentPlayers** — Tournament enrollment
- **TournamentNotificationPreference** — Per-user, per-tournament match notification level (`MatchNotificationLevel` enum)
- **StreamRoom** — Named stream stage (Stage 1, Stage 2, etc.)
- **Commentator** / **Tracker** — Crew signups with approval workflow
- **GeneratedSeeds** — Randomizer seed URLs linked to matches
- **TriforceText** — Player-submitted ALTTP end-game triforce screen lines; approval tracked per entry
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

Discord OAuth is handled by `middleware/auth.py`. User identity is stored in NiceGUI's `app.storage.user` (key: `discord_id`). Access control is role-based via `UserRole` — there is no `permission` field on `User`.

Use `AuthService` from `application/services/auth_service.py` to check access:

```python
from application.services.auth_service import AuthService, current_user_from_storage
from models import Role

user = await current_user_from_storage()   # returns User or None

# Check a global role
if await AuthService.has_role(user, Role.STAFF):
    ...

# Check a set of roles (returns set[Role])
roles = await AuthService.get_roles(user)
if Role.PROCTOR in roles:
    ...

# Higher-level helpers
if await AuthService.can_view_admin(user):  # any admin role or tournament/crew membership
    ...
if await AuthService.can_crud_match(user, match):
    ...
```

Use `@protected_page('/path')` for routes that require login. Pass `roles=` to also enforce a specific role at the route level:

```python
from middleware.auth import protected_page
from models import Role

@protected_page('/admin', roles=[Role.STAFF])
async def admin_only_page():
    ...
```

## Coding Conventions

- **Async everywhere** — all DB calls and UI handlers must be `async def`
- **Type hints** — use throughout; helps IDE support and documents intent
- **No direct ORM writes in UI** — always go through the service layer
- **Read-only ORM queries from UI are acceptable** for simple display lookups, but prefer repositories
- **Raise `ValueError` for user errors** in services; catch in UI and show `ui.notify(str(e), color='warning')`
- **Audit important actions** — use `AuditService` for creates, updates, deletes (see "Audit log action conventions" below)
- **No comments explaining what code does** — only add a comment for a non-obvious constraint, workaround, or invariant
- **Keep services stateless** — instantiate per-request or use static methods

### Audit log action conventions

- Action strings are namespaced `verb.object` — e.g. `match.created`, `user.role_granted`, `system_config.updated`. Use a constant from `application.services.audit_service.AuditActions` rather than a literal string; add a new constant there when introducing a new action.
- Pass `actor: User` explicitly. `AuditService.write_log` raises `ValueError` when actor is `None` — do not wrap calls in `if actor:` guards.
- Pass `details` as a plain dict (e.g. `{'match_id': match.id, 'changed_fields': [...]}`). The service JSON-encodes it; the audit viewer renders it expandable.

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

The three-layer refactor is largely complete. All major domains have repositories and services. See `docs/refactoring-guide.md` for patterns and examples.

**Repositories** (`application/repositories/`):
`commentator`, `match`, `stream_room`, `tournament`, `tracker`, `user`

**Services** (`application/services/`):
`auth`, `audit`, `crew`, `discord`, `match`, `match_schedule`, `reports`, `seedgen`, `stream_room`, `tournament`, `user`

When touching any area, prefer the three-layer pattern over adding direct ORM queries to the UI layer.

## Reference Documents

| File | Purpose |
|---|---|
| `docs/current-state.md` | Active project state — feature status, known issues, key files |
| `docs/design.md` | Original requirements and page structure |
| `docs/refactoring-guide.md` | Detailed three-layer architecture guide with code examples |
| `docs/timezone-handling.md` | Datetime/timezone implementation details |
| `docs/ux-audit.md` | Full UX audit with findings by theme and severity |
| `docs/features/` | Per-feature docs for all Claude-built features |
| `migrations/tortoise_config.py` | DB connection configuration |
| `start.sh` | Server startup commands |
| `pyproject.toml` | Dependencies and Aerich config |
| `nicegui/llms.md` (in installed package) | Authoritative NiceGUI API reference for AI assistants — fetch before writing NiceGUI code |
