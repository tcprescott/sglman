# Wizzrobe

A web application for managing tournament schedules, matches, players, crew, and online races for [SpeedGaming Live](https://www.speedgaming.org/) events. Wizzrobe runs both **on-site restream events** (players physically present, staff scheduling matches onto stream stages) and **online tournaments** (remote racing on racetime.gg, automated seed distribution, async qualifiers) — and is the designated successor to [SahasrahBot](https://github.com/tcprescott/sahasrahbot).

Built with FastAPI + NiceGUI, backed by PostgreSQL, integrated with Discord for authentication and notifications, and **logically multitenant** so one deployment hosts many independent communities.

> The GitHub repository is named `sglman`; the Python package and product are **Wizzrobe**.

## Features

### On-site event management
- **Match scheduling & lifecycle** — create, edit, and track matches through Scheduled → Checked In → In Progress → Finished
- **Stream room assignment** — assign matches to named stages and track what's on air
- **Player dashboard** — players see upcoming matches, acknowledge schedules, and submit triforce text
- **Crew coordination** — commentator and tracker signup with an admin approval workflow (web + Discord DM buttons)
- **Volunteer scheduling** — opt-in positions, shifts, availability, an auto-scheduler, and reminders
- **Equipment lending** — assets, checkout/check-in, loan history, and QR codes
- **Player availability** — self-service availability windows that feed match-time suggestions
- **Triforce text submissions** — ALTTP end-game screen text submission and moderation per tournament
- **Reports & insights** — match ops, crew hours, capacity, stream room, audit-log, and trended analytics reports

### Online tournaments
- **User-managed seed presets** — tenant-authored presets drive seed generation across multiple randomizers (ALTTPR, OOTR, SM Map Rando, DK64, …), no code change per tournament
- **Racetime.gg room lifecycle** — rooms auto-open ahead of scheduled matches, drive through finish/cancel, attach the seed, and capture results
- **Async qualifiers** — self-paced permalink-pool qualifiers with par scoring, a reviewer queue, and synchronous live races
- **SpeedGaming schedule ETL** — one-way sync of SpeedGaming episodes into matches, with placeholder users for unresolved players
- **Discord Scheduled Events sync** — idempotent mirroring of the schedule into each community's Discord server

### Platform & integrations
- **Multitenancy** — many communities from one deployment, addressed by `/t/<slug>` path or a custom domain, with a `/platform` super-admin surface
- **Per-tenant feature flags** — deliberately-gated subsystems, disabled by default, managed per community
- **Role-based access control** — eleven roles spanning community staff, online-tournament admins, and the global super-admin
- **Discord integration** — OAuth login, one bot serving many guilds, guild-role → app-role sync, and DM notifications
- **Web push** — device notifications (iOS/Android/desktop) mirroring Discord DMs
- **REST API** — full read/write API authenticated by personal access tokens
- **Event bus & webhooks** — an in-process event bus with staff-managed signed outbound webhooks
- **Engagement telemetry**, **audit logging**, **in-app feedback**, and **Challonge / Twitch / racetime.gg** identity linking

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python ≥3.12 |
| Web framework | FastAPI ≥0.136 |
| UI framework | NiceGUI ≥3.12 |
| ORM | Tortoise ORM ≥0.24 (asyncpg) |
| Migrations | Aerich ≥0.8 |
| Database | PostgreSQL 16 |
| Discord bot | py-cord ≥2.6 |
| Discord OAuth | zenora |
| Seed generation | pyz3r (ALTTPR) + HTTP APIs for other randomizers |
| Package manager | Poetry |
| Container | Docker + docker-compose |

Authoritative versions live in [`pyproject.toml`](pyproject.toml).

## Documentation

Developer documentation lives in [`docs/`](docs/README.md):

- [Architecture overview](docs/architecture.md) — how the pieces fit together
- [Current state](docs/current-state.md) — living status snapshot of every feature
- [Development guide](docs/development.md) — local setup, mock Discord mode, fixtures, tests
- [Deployment guide](docs/deployment.md) — Docker, the authoritative environment-variable table, operations
- [Code reference](docs/README.md#code-reference-docsreference) — data model, services, REST API, auth, Discord, seed generation, frontend
- [Feature docs](docs/README.md#feature-reference-docsfeatures) — implementation notes per feature

## Quick Start

### Local development

```bash
poetry install
cp .env.example .env    # set STORAGE_SECRET; for a no-Discord loop set MOCK_DISCORD=true and ENVIRONMENT=development
./start.sh dev          # runs on http://localhost:8000 with auto-reload
```

`MOCK_DISCORD=true` swaps Discord OAuth for a local user-picker and stubs all Discord calls, so the full app is developable without a Discord application. See the [development guide](docs/development.md) for the mock-Discord loop and dev fixtures (`scripts/seed_dev.py`).

### Docker

```bash
docker-compose up       # builds and starts the app + postgres on port 8000
```

### Database migrations

```bash
poetry run aerich migrate   # generate a migration from model changes
poetry run aerich upgrade   # apply pending migrations
```

Migrations also run automatically on startup.

## Environment Variables

Core variables to get started:

| Variable | Required | Description |
|---|---|---|
| `DB_HOST` | yes | PostgreSQL hostname |
| `DB_PORT` | yes | PostgreSQL port (default `5432`) |
| `DB_NAME` | yes | Database name |
| `DB_USERNAME` / `DB_PASSWORD` | prod | Database credentials (enforced when `ENVIRONMENT=production`) |
| `STORAGE_SECRET` | yes | NiceGUI session storage encryption key |
| `ENVIRONMENT` | no | `development` (default) or `production` |
| `MOCK_DISCORD` | no | `true` bypasses Discord OAuth (user-picker at `/login`) and stubs Discord; refused in production |
| `DISCORD_TOKEN` | for Discord | Discord bot token (not needed in mock mode) |
| `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` | for Discord | Discord OAuth app credentials |
| `BASE_URL` | no | Public base URL (default `http://localhost:8000`); derives the OAuth redirect URI |

The **authoritative, complete** environment-variable table — including the online-tournament workers, multitenancy (`PLATFORM_HOST`), web push (VAPID), telemetry, and randomizer API keys — lives in the [deployment guide](docs/deployment.md#environment-variables) and is kept in sync with [`application/utils/environment.py`](application/utils/environment.py) and [`.env.example`](.env.example).

## API Docs

When the server is running:
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

## License

Dual-licensed by Thomas Prescott: publicly under the [GNU GPL v3.0](LICENSE), and separately under other terms at his discretion. See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.
