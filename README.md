# Wizzrobe

A web application for managing tournament schedules, matches, players, and crew for Wizzrobe onsite events. Built with FastAPI + NiceGUI, backed by PostgreSQL, and integrated with Discord for authentication and notifications.

## Features

- **Schedule management** — create, edit, and track match lifecycle (Scheduled → Checked In → In Progress → Finished)
- **Stream room assignment** — assign matches to named stream stages and track what's on air
- **Player dashboard** — players see their upcoming matches, acknowledge schedules, and submit triforce text
- **Crew coordination** — commentator and tracker signup with admin approval workflow
- **Role-based access control** — Staff, Proctor, and Stream Manager roles plus per-tournament admin and crew-coordinator membership
- **Discord integration** — OAuth login and bot notifications
- **Triforce text submissions** — ALTTP end-game screen text submission and moderation per tournament
- **Reports** — match ops, crew, capacity, stream room, and audit log reports

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI ≥0.136 |
| UI framework | NiceGUI ≥3.12 |
| ORM | Tortoise ORM ≥0.24 |
| Migrations | Aerich ≥0.8 |
| Database | PostgreSQL 16 |
| Auth | Discord OAuth |
| Package manager | Poetry |
| Container | Docker + docker-compose |

Authoritative versions live in [`pyproject.toml`](pyproject.toml).

## Documentation

Full developer documentation lives in [`docs/`](docs/README.md):

- [Architecture overview](docs/architecture.md) — how the pieces fit together
- [Development guide](docs/development.md) — local setup, mock Discord mode, tests
- [Deployment guide](docs/deployment.md) — Docker, environment variables, operations
- [Code reference](docs/README.md#code-reference-docsreference) — data model, services, REST API, auth, Discord, seed generation, frontend
- [Feature docs](docs/README.md#feature-reference-docsfeatures) — implementation notes per feature

## Quick Start

### Local development

```bash
poetry install
cp .env.example .env   # fill in credentials (see Environment Variables below)
./start.sh dev         # runs on http://localhost:8000 with auto-reload
```

### Docker

```bash
docker-compose up      # builds and starts the app + postgres on port 8000
```

### Database migrations

```bash
poetry run aerich migrate   # generate migration from model changes
poetry run aerich upgrade   # apply pending migrations
```

Migrations also run automatically on startup.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DB_HOST` | yes | PostgreSQL hostname |
| `DB_PORT` | yes | PostgreSQL port (default `5432`) |
| `DB_NAME` | yes | Database name |
| `DB_USERNAME` | no | Database user |
| `DB_PASSWORD` | no | Database password |
| `DISCORD_TOKEN` | yes | Discord bot token |
| `DISCORD_CLIENT_ID` | yes | Discord OAuth app client ID |
| `DISCORD_CLIENT_SECRET` | yes | Discord OAuth app client secret |
| `BASE_URL` | no | Public base URL of the app (default `http://localhost:8000`); used to derive the OAuth redirect URI |
| `REDIRECT_URL` | no | Override the derived OAuth callback URL (`{BASE_URL}/oauth/callback`) |
| `OAUTH_URL` | no | Override the derived Discord OAuth authorize URL |
| `STORAGE_SECRET` | yes | NiceGUI session storage encryption key |
| `ENVIRONMENT` | no | `development` (default) or `production` |
| `MOCK_DISCORD` | no | Set `true` to bypass Discord OAuth (shows a user-picker at `/login`); stubs all Discord calls. Useful for local dev without a real Discord app. |

## API Docs

When the server is running:
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`
