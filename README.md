# Wizzrobe

Wizzrobe runs tournaments for speedrunning and randomizer communities. It schedules matches onto stream stages, lines up commentators and trackers for each one, rolls the seeds, staffs the volunteer rota, lends out equipment and checks people in at the door. It was built for [SpeedGaming Live](https://www.speedgaming.org/), which uses it to run its in-person event, and it also handles online tournaments raced on [racetime.gg](https://racetime.gg/). It's the successor to [SahasrahBot](https://github.com/tcprescott/sahasrahbot).

One deployment hosts many independent communities. Each one lives at its own `/t/<slug>` address (or its own domain), with its own staff, roles, branding, Discord server and settings, and nothing crosses between them.

## What it does

**For players**

- See your matches, opponents, stage and stream on one schedule, acknowledge them, and get a Discord DM when anything changes.
- Sign up for tournaments, set your availability, and request a reschedule or cancellation.
- Book your own match times from a Challonge bracket, or play in brackets run inside Wizzrobe (single and double elimination, Swiss, round robin, best-of-N series).
- Race async qualifiers and online matches with seeds rolled for you.
- Leave a note on a match for the staff running it (your opponent never sees it), and get a DM when staff message you about one.

**For crew and volunteers**

- Sign up to commentate, track or restream a match and get approved by a coordinator.
- Pick up volunteer shifts, see your schedule, and get reminders before each one.
- Proctors get a board of every match in their room, grouped by what each one needs next (check in, start, finish), with the button for that step on each line.

**For staff**

- A run-sheet board for the whole event: schedule, assign stages, roll seeds, record results, rewind a match to an earlier step when something goes wrong.
- Seed presets for each randomizer (A Link to the Past, Ocarina of Time, Super Metroid, Donkey Kong 64, Final Fantasy, Zelda 1, Wind Waker and more), with built-in presets you can import.
- A phone-first check-in desk synced from the event's Matcherino roster.
- Equipment lending with printable QR labels (which can carry the community's logo).
- Prize payouts, ADA accommodation requests, community events, triforce texts, in-app feedback, and reports on how the event is going, including which parts of the app people actually use.
- Discord role sync, Discord Scheduled Events, and a SpeedGaming schedule sync.

**For viewers**

- A public Watch page with the stream player, what's on each stage, what's coming up, and links to every tournament's bracket and rules. It needs no sign-in.

Everyone gets an in-app help section, a weekly "What's new" page, light and dark mode, and a layout that works the same on a phone as on a desktop. Several of the larger subsystems (brackets, check-in, payouts and others) are per-community feature flags that start switched off.

For developers there's a token-authenticated REST API, a remote [MCP server](docs/features/mcp-server.md) so AI assistants can read (and, with consent, update) a community's data, signed outbound webhooks, and web push.

[docs/current-state.md](docs/current-state.md) is the up-to-date status of every feature.

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI |
| UI | NiceGUI (Vue + Quasar) |
| Database | PostgreSQL 16 via Tortoise ORM (asyncpg), migrations with Aerich |
| Sessions | Redis (optional, keeps people signed in across restarts) |
| Discord | discord.py bot, OAuth sign-in |
| Packaging | Poetry, Docker + docker compose |

Exact versions are in [`pyproject.toml`](pyproject.toml).

## Getting started

You don't need a Discord application or any randomizer keys to run Wizzrobe locally. Mock mode replaces Discord sign-in with a user picker and fakes every outside service.

You'll need Python 3.12+, [Poetry](https://python-poetry.org/), and a PostgreSQL 16 database (Docker is the easiest way to get one).

```bash
git clone https://github.com/tcprescott/wizzrobe.git
cd wizzrobe
poetry install
cp .env.example .env
```

In `.env`, set `STORAGE_SECRET` to any long random string, and set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USERNAME` and `DB_PASSWORD` for your database. If you use the compose file's `postgres` service, note that it doesn't publish a port to your machine, so add `ports: ["5432:5432"]` to it first, then:

```bash
docker compose up -d postgres
./start.sh mock                          # http://localhost:8000
poetry run python scripts/seed_dev.py    # in another terminal: sample communities, tournaments, matches and users
```

Migrations run on startup, so the first boot creates the schema. Always start the app through `start.sh`, because it's the only thing that loads `.env`. `./start.sh dev` uses real integrations instead of mocks, and `./start.sh stop` stops whichever one is running.

The [development guide](docs/development.md) covers the rest: the mock identities, the dev fixtures, migrations, the test suite and CI.

### Running the full stack in Docker

```bash
docker compose up
```

This builds the image and starts the app, PostgreSQL and Redis on port 8000. It runs whatever `.env` says, and the template ships with `ENVIRONMENT=production`, which needs real Discord credentials and refuses mock mode. Every setting is listed in the [deployment guide](docs/deployment.md#environment-variables).

### Tests

```bash
poetry run pytest
```

The suite uses in-memory SQLite, so it needs no database. CI also runs linting, type checks, architecture checks and an accessibility scan of every page in a real browser, light and dark, at phone and desktop widths.

### API

With the server running, the REST API is documented at `http://localhost:8000/api/docs` (Swagger) and `/api/redoc`. See the [REST API reference](docs/reference/rest-api.md) for personal access tokens and what each one can reach.

## How the code is organised

Wizzrobe follows a three-layer pattern: pages call services, services call repositories, repositories talk to the models. The web UI, the REST API, the Discord bot and the MCP server are all thin entry points over the same services, and guardrail checks in CI enforce the boundaries.

| Path | What's there |
|---|---|
| `pages/`, `theme/`, `static/` | NiceGUI pages, shared UI components, CSS and JS |
| `application/services/` | Business rules, validation, audit logging, notifications |
| `application/repositories/` | Data access, scoped to the current community |
| `models/` | Tortoise ORM models |
| `api/`, `discordbot/`, `mcpserver/`, `racetimebot/` | REST API, Discord bot, MCP server, racetime.gg bot |
| `migrations/` | Aerich migrations |
| `scripts/` | Dev seed data, validation and CI helpers |
| `tests/` | pytest suite |

## Documentation

Everything lives in [`docs/`](docs/README.md). Good places to start:

- [Architecture](docs/architecture.md) for how the pieces fit together
- [Development guide](docs/development.md) for local setup, mock mode, tests and CI
- [Deployment guide](docs/deployment.md) for Docker, environment variables and operations
- [Refactoring guide](docs/refactoring-guide.md) for the three-layer pattern with examples
- [Style guide](docs/style-guide.md) for the UI design system and accessibility rules (read it before touching any page)
- [Multitenancy](docs/features/multitenancy.md) and [feature flags](docs/features/feature-flags.md)
- The [code reference](docs/README.md#code-reference-reference) (data model, services, frontend, auth, Discord, seed generation) and [per-feature docs](docs/README.md#features-features)

[CLAUDE.md](CLAUDE.md) is the short list of rules every change is expected to follow, written for AI coding assistants but just as useful for people.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first, because it explains the licensing terms that come with a contribution. Any PR that changes what people see in the app adds a line to the in-app changelog (see the [changelog doc](docs/features/changelog.md)).

To report a security problem, follow [SECURITY.md](SECURITY.md) rather than opening a public issue.

## License

Dual-licensed by Thomas Prescott: publicly under the [GNU GPL v3.0](LICENSE), and separately under other terms at his discretion.
