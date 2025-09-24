# Copilot Instructions for SGLMan

## Project Overview
SGLMan is a FastAPI + NiceGUI application for managing tournament schedules, matches, users, and crew for speedgaming events. It uses Tortoise ORM for database access and Aerich for migrations. The app integrates with Discord for authentication and user management.

## Architecture & Key Components
- **main.py**: FastAPI app entry point; initializes DB, sets up API and frontend routes, manages app lifespan.
- **frontend.py**: Registers NiceGUI pages and attaches them to FastAPI.
- **models.py**: Tortoise ORM models for users, teams, matches, tournaments, etc. Permissions are managed via an `IntEnum`.
- **migrations/**: Aerich migration scripts and Tortoise config (`tortoise_config.py`).
- **pages/**: UI pages (`home.py`, `schedule.py`, `player.py`, `crew.py`, `admin.py`). Each page is registered via `@ui.page` and uses NiceGUI components.
- **theme/dialog/** & **theme/tables/**: Custom dialog and table components for UI interactions (e.g., `UserDialog`, `MatchTableView`, `TournamentDialog`, `MatchDialog`).
- **application/**: Business logic modules (e.g., `audit.py` for audit logging, `match.py` for match creation).
- **api.py**: FastAPI API routes (minimal, expand as needed).
- **.env**: Environment variables for DB and Discord credentials.
- **discordbot/**: Discord bot integration (not fully implemented).

## Developer Workflows
- **Install dependencies**: `poetry install`
- **Run dev server**: `./start.sh dev` (port 8080, auto-reloads)
- **Run prod server**: `./start.sh prod` (port 80)
- **Database migrations**: Use Aerich (`poetry run aerich migrate`, `poetry run aerich upgrade`). Config in `pyproject.toml` and `migrations/tortoise_config.py`.
- **Environment variables**: Set DB and Discord credentials in `.env` (see `migrations/tortoise_config.py` and `pages/home.py`).

## Patterns & Conventions
- **Async/await**: All DB and UI actions are async; dialogs and page actions use async functions. Audit logging and match creation use async helpers in `application/`.
- **NiceGUI**: UI logic is declarative, using `ui.page`, `ui.dialog`, `ui.card`, etc. Dialogs are modular (see `theme/dialog/`).
- **User authentication**: Managed via Discord OAuth and NiceGUI storage (`app.storage.user`).
- **Permissions**: Use `Permissions` enum in `models.py`; check `user.permission` for access control.
- **Admin workflows**: Admin dashboard (`/admin`) provides tabs for schedule, users, tournaments, and settings. Dialogs for editing/creating users, matches, tournaments.
- **Crew management**: `/crew` page for crew signup and approval by privileged users.
- **API**: Minimal, but extendable via FastAPI routers in `api.py`.

## Integration Points
- **Discord**: OAuth login, user info, and messaging (see `pages/home.py`, `models.py`).
- **Database**: MySQL via Tortoise ORM; config in `.env` and `migrations/tortoise_config.py`.

## Examples
- To add a new page: create a file in `pages/`, define a `create()` function with `@ui.page`, and register it in `frontend.py`.
- To add a dialog: create a class in `theme/dialog/`, use NiceGUI components, and call from a page or table. For tournament dialogs, see `TournamentDialog` in `theme/dialog/tournament_edit_dialog.py` (supports bracket URL, rules URL, format, match durations).
- To add audit logging: use `write_audit_log(user, action, details)` from `application/audit.py`.
- To create a match: use `create_match(...)` from `application/match.py`.
- To add a model: define a Tortoise `Model` in `models.py`, run Aerich migrations.

## References
- See `DESIGN.md` for requirements and page structure.
- See `start.sh` for server commands.
- See `pyproject.toml` for dependencies and Aerich config.

---
If any section is unclear or missing, please provide feedback for further refinement.