# Wizzrobe

A web application for managing tournament schedules, matches, players, crew, and online races for [SpeedGaming Live](https://www.speedgaming.org/) events. Wizzrobe runs both **on-site restream events** (players physically present, staff scheduling matches onto stream stages) and **online tournaments** (remote racing on racetime.gg, automated seed distribution, async qualifiers) — and is the designated successor to [SahasrahBot](https://github.com/tcprescott/sahasrahbot).

Built with FastAPI + NiceGUI, backed by PostgreSQL, integrated with Discord for authentication and notifications, and **logically multitenant** so one deployment hosts many independent communities.

> The GitHub repository is named `sglman`; the Python package and product are **Wizzrobe**.

## Features

- **On-site event management** — match scheduling and lifecycle, stage assignment, a player dashboard, crew signup and approval, volunteer scheduling, equipment lending, player availability, triforce-text submissions, and operational reports.
- **Online tournaments** — tenant-authored seed presets across multiple randomizers, racetime.gg room lifecycle, async qualifiers, SpeedGaming schedule ETL, and Discord Scheduled Events sync.
- **Platform & integrations** — multitenancy with a `/platform` super-admin surface, per-tenant feature flags, role-based access control, Discord (OAuth, one bot for many guilds, role sync, DMs), web push, a token-authenticated REST API, a remote MCP server, an event bus with outbound webhooks, telemetry, audit logging, and Challonge / Twitch / racetime.gg identity linking.

[docs/current-state.md](docs/current-state.md) is the living per-feature status list.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python ≥3.12 |
| Web framework | FastAPI ≥0.136 |
| UI framework | NiceGUI ≥3.12 |
| ORM | Tortoise ORM ≥0.24 (asyncpg) |
| Migrations | Aerich ≥0.8 |
| Database | PostgreSQL 16 |
| Discord bot | discord.py ≥2.7 |
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
- [Code reference](docs/README.md#code-reference-reference) — data model, services, REST API, auth, Discord, seed generation, frontend
- [Feature docs](docs/README.md#features-features) — implementation notes per feature

## Quick Start

### Local development

```bash
poetry install
cp .env.example .env    # set STORAGE_SECRET and the DB_* values
./start.sh mock         # http://localhost:8000, auto-reload, no external credentials
```

`./start.sh mock` forces `ENVIRONMENT=development` plus the `MOCK_DISCORD`/`MOCK_SEEDGEN`/`MOCK_CHALLONGE`/`MOCK_TWITCH`/`MOCK_RACETIME` flags: Discord OAuth becomes a local user-picker, Discord calls are stubbed, seeds return fake permalinks, and the three account-linking providers answer with canned identities — so the full app is developable with no Discord, randomizer or provider credentials. Use `./start.sh dev` when you want real integrations. See the [development guide](docs/development.md) for the mock loop and dev fixtures (`scripts/seed_dev.py`).

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

To boot you need `DB_HOST`, `DB_PORT`, `DB_NAME` and `STORAGE_SECRET`; `DB_USERNAME`/`DB_PASSWORD` are additionally enforced when `ENVIRONMENT=production`.

The **authoritative, complete** table — Discord, multitenancy (`PLATFORM_HOST`), the online-tournament workers, web push, telemetry, the `MOCK_*` flags and more — lives in the [deployment guide](docs/deployment.md#environment-variables), alongside the annotated [`.env.example`](.env.example) template.

## API Docs

When the server is running:
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

## License

Dual-licensed by Thomas Prescott: publicly under the [GNU GPL v3.0](LICENSE), and separately under other terms at his discretion. See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.
