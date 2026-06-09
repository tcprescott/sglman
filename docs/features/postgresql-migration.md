# Feature: PostgreSQL Database

_Added: PR #15 (MySQL → PostgreSQL), PR #16 (Docker + GHCR CI) | Status: Stable_

## What Changed (PR #15)

The application was originally backed by MySQL. PR #15 migrated to PostgreSQL:

- `tortoise_config.py` updated to use `tortoise.backends.asyncpg`.
- All Aerich migrations regenerated for PostgreSQL syntax.
- `pyproject.toml` dependencies: replaced `aiomysql` with `asyncpg`.
- `docker-compose.yml` updated to use `postgres:16` image.
- Migration SQL compatibility: MySQL-specific syntax (`AUTO_INCREMENT`, backtick quoting) removed.

## Docker Setup (PR #16)

`docker-compose.yml` defines two services:

| Service | Image | Purpose |
|---|---|---|
| `app` | Built from `Dockerfile` | The SGLMan application |
| `db` | `postgres:16-alpine` | PostgreSQL database |

The `app` container waits for `db` to be healthy before starting (healthcheck configured).

## CI: GitHub Actions / GHCR Publish (PR #16)

`.github/workflows/publish.yml` builds and pushes the container image to GitHub Container Registry on every push to `main`:

```
ghcr.io/tcprescott/sglman:latest
ghcr.io/tcprescott/sglman:<sha>
```

## Connection Configuration

All connection parameters are in environment variables, read by `migrations/tortoise_config.py`:

```
DB_HOST, DB_PORT, DB_NAME, DB_USERNAME, DB_PASSWORD
```

## Migrations

```bash
poetry run aerich migrate   # generate migration from model changes
poetry run aerich upgrade   # apply pending migrations

# Or via Docker:
docker-compose exec app poetry run aerich upgrade
```

Migrations run automatically on startup via `main.py:init_db()`.

## Local Dev Without Docker

```bash
# Run postgres locally or via a minimal docker container
docker run -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=sglman -p 5432:5432 postgres:16-alpine

# Set in .env:
DB_HOST=localhost
DB_PORT=5432
DB_NAME=sglman
DB_USERNAME=postgres
DB_PASSWORD=pass
```
