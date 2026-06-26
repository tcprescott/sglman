# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in SGLMan, please report it privately
rather than opening a public issue.

- Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  ("Report a vulnerability" under the repository's **Security** tab), or
- Contact the maintainer directly.

Please include enough detail to reproduce the issue (affected endpoint/page,
steps, and impact). We aim to acknowledge reports promptly and will coordinate
disclosure once a fix is available.

## Supported configuration

SGLMan is designed to run as a single Uvicorn worker behind a TLS-terminating
reverse proxy. Security-relevant configuration is validated at startup
(`application/utils/environment.py`):

- `STORAGE_SECRET` is required in every environment and must be at least 32
  characters in production (it signs the session store the authorization model
  trusts).
- `DB_USERNAME` / `DB_PASSWORD` are required in production.
- `MOCK_DISCORD` / `MOCK_CHALLONGE` are refused in production.
- Set `TRUST_PROXY_FORWARDED_FOR=true` only when a trusted reverse proxy
  overwrites the `X-Forwarded-For` header.

## Security practices in this project

- All REST endpoints require a personal bearer token; tokens are stored only as
  SHA-256 hashes, support expiry/revocation, and honor a read-only flag.
- Authorization is enforced in the service layer (the single write path for both
  the web UI and the Discord bot).
- Data access is exclusively through the Tortoise ORM (no raw SQL).
- Dependencies are scanned with `pip-audit` in CI (`.github/workflows/security.yml`).
