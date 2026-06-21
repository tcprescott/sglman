# SGLMan Security Audit

_Audit date: 2026-06-21 — scope: full codebase (`main` at audit time), static review only._

This is a point-in-time, read-only security review of the SGLMan FastAPI + NiceGUI
application: authentication/authorization, the REST API, injection/input handling,
secrets/configuration, and deployment. No changes to application behavior were made
as part of this audit; remediation items are listed per finding.

## Executive summary

The codebase is in **good security health**. The three-layer architecture is applied
consistently, all REST endpoints are authenticated, the service layer is the single
choke point for authorization, and database access is exclusively through the Tortoise
ORM (no raw SQL). Secrets are environment-sourced, startup fail-fast validation is in
place, Sentry events are scrubbed, and the container runs as a non-root user.

No Critical or High severity issues were found. The one finding worth prompt attention
is a **stored XSS** through markdown rendering of a tournament-admin-controlled field.
The remaining items are low-severity defense-in-depth / hardening improvements.

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | Stored XSS via `ui.markdown(tournament.triforce_access_message)` | Medium | **Fixed** |
| 2 | API endpoints use `require_write_actor` where docstring says "Staff only" | Low | **Fixed** |
| 3 | Rate-limit key trusts `X-Forwarded-For` | Low | **Fixed** |
| 4 | No HTTP security headers (CSP / X-Frame-Options / X-Content-Type-Options / HSTS) | Low | **Fixed** |
| 5 | Production image ships dev dependencies | Low / Info | **Fixed** |
| 6 | No `SECURITY.md` / dependency scanning in CI | Info | **Fixed** |

All findings have been remediated on the `claude/security-audit-1yufd9` branch; per-finding
details and the exact fix are recorded under each finding below.

### Verified-clean areas (no action needed)

- **SQL injection** — all data access goes through Tortoise ORM query builders; no
  `.raw()`, `execute_query`, or string-built SQL anywhere.
- **SSRF** — outbound HTTP (seed generation in `application/services/seedgen_service.py`)
  targets hardcoded hosts (`maprando.com`, `ootrandomizer.com`); no user-controlled URLs
  are fetched. `tournament.bracket_url` / `rules_url` are stored but never fetched.
- **Path traversal / file handling** — no file uploads; preset file paths are all
  hardcoded; CSV export writes to an in-memory `StringIO`.
- **Deserialization / RCE** — no `eval`/`exec`/`pickle`/`subprocess`; YAML uses
  `yaml.safe_load`; config/audit JSON parsing is wrapped in `try/except`.
- **OAuth CSRF** — both the Discord (`middleware/auth.py`) and Challonge
  (`middleware/challonge_oauth.py`) flows generate a one-time `state` token and validate
  it on callback; the post-login redirect is whitelisted against open-redirect.
- **API token handling** — high-entropy tokens (`secrets.token_urlsafe(32)`), stored only
  as SHA-256 hashes, with expiry, revocation, per-user ownership, and a read-only flag
  enforced on mutating routes (`api/dependencies.py`).
- **CSV formula injection** — `application/utils/csv_export.py` prefixes `= + - @` cells.
- **Secrets & logging** — no hardcoded secrets; tokens logged by 17-char prefix only;
  Sentry `before_send` filters `authorization`/`cookie`/`x-api-key`, `send_default_pii=False`.

### Corrected from the working notes (false positives)

- `GET /api/matches/{match_id}` **is** authenticated — its router declares a router-level
  `dependencies=[Depends(require_api_actor)]` (`api/routers/matches.py:18`), which applies
  to every route on the router including the single-match getter.
- Discord credentials held in the module-level `config` dict and the production-disabled
  API docs are **not** vulnerabilities.

---

## Findings

### 1. Stored XSS via markdown rendering of `triforce_access_message` — Medium

**Location:** `pages/home_tabs/triforce_texts.py:94`

```python
if tournament.triforce_access_message:
    ui.markdown(tournament.triforce_access_message)
```

**Issue.** NiceGUI's `ui.markdown()` passes raw HTML through to the page by default — it
does not sanitize embedded tags. The `triforce_access_message` field is writable by any
**per-tournament admin**, not only global Staff: `TournamentService.update_tournament`
authorizes via `AuthService.can_edit_tournament` (`application/services/tournament_service.py:93`),
which returns true for Staff *or* a tournament admin. The rendered message is shown to
**every player** who opens that tournament's triforce-texts page and is not allowed to
submit.

This crosses a privilege boundary: a semi-trusted, per-tournament admin (a role Staff may
grant to community volunteers) can inject markup such as `<img src=x onerror=...>` that
executes JavaScript in the browser of any visitor — including Staff who view the page —
enabling session/CSRF actions in the victim's context.

**Severity rationale.** Requires a (semi-)privileged account to plant the payload, but the
audience is broad and includes higher-privileged users → Medium.

**Remediation (pick one):**
- Sanitize the value before rendering (e.g. `bleach.clean(...)` with a small allowlist of
  formatting/link tags), or
- Render as plain text with `ui.label(...)` (with `white-space: pre-wrap`) if rich
  formatting is not required, or
- Render markdown with HTML escaped first, then only re-enable a safe subset.

Whichever is chosen, apply the same treatment to any other free-text field surfaced via
`ui.markdown()` / `ui.html()` in the future. Also validate the URL scheme (reject
`javascript:` etc.) if `bracket_url` / `rules_url` are ever rendered as live links —
today they are only echoed into the edit form, so this is informational.

**Fixed.** `pages/home_tabs/triforce_texts.py` now renders the message as plain text via
`ui.label(...).style('white-space: pre-wrap')` instead of `ui.markdown(...)`, eliminating
HTML/script passthrough. This was the only dynamic `ui.markdown`/`ui.html` sink in the UI.
The added security headers (finding #4) provide a second layer.

### 2. Endpoint decorators looser than their "Staff only" docstrings — Low

**Locations:**
- `api/routers/discord_role_mappings.py` — `add_mapping` / `remove_mapping` use
  `require_write_actor`
- `api/routers/system_config.py:41` — `set_config` uses `require_write_actor`

These routes document "Staff only" but gate on `require_write_actor` (any authenticated
user with a non-read-only token). **They are not exploitable**: the underlying services
re-check Staff (`DiscordRoleMappingService` via `AuthService.can_grant_roles`,
`SystemConfigService` via its Staff check) and raise `PermissionError` → 403. This is a
defense-in-depth / clarity gap only.

**Remediation.** Swap these endpoints to `Depends(require_staff)` so the HTTP-layer gate
matches the documented contract (the GET counterparts already use `require_staff`).

**Fixed.** Added a `require_staff_write` dependency (`api/dependencies.py`) that resolves the
token, rejects read-only tokens, *and* requires the Staff role — preserving the read-only
enforcement that a plain `require_staff` would have dropped. The three mutating routes
(`discord_role_mappings.add_mapping`/`remove_mapping`, `system_config.set_config`) now use it.

### 3. Rate-limit key trusts `X-Forwarded-For` — Low

**Location:** `api/rate_limit.py:38-41`

```python
forwarded = request.headers.get('x-forwarded-for')
if forwarded:
    return f'ip:{forwarded.split(",")[0].strip()}'
```

For requests without a bearer token, the limiter buckets by the client-supplied
`X-Forwarded-For` header, which an attacker can rotate freely to evade the per-IP limit.
Impact is bounded because all API endpoints require a token (those requests are bucketed
by token, not IP), so the IP path mainly governs unauthenticated `401` traffic.

**Remediation.** Only trust `X-Forwarded-For` when behind a known reverse proxy (e.g. take
the right-most untrusted hop, or use Starlette's `ProxyHeadersMiddleware` / a configured
trusted-proxy count); otherwise fall back to `request.client.host`.

**Fixed.** `api/rate_limit.py` now ignores `X-Forwarded-For` unless
`TRUST_PROXY_FORWARDED_FOR` is explicitly enabled, defaulting to the real socket peer
(`request.client.host`).

### 4. Missing HTTP security headers — Low

No middleware sets `Content-Security-Policy`, `X-Frame-Options` (or CSP `frame-ancestors`),
`X-Content-Type-Options: nosniff`, or `Strict-Transport-Security`. The app relies on a
signed session cookie, so a CSP and anti-clickjacking headers add meaningful
defense-in-depth (and a strong CSP would substantially blunt finding #1).

**Remediation.** Add a small response-header middleware (or configure one at the reverse
proxy) setting at minimum `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` /
CSP `frame-ancestors 'none'`, `Strict-Transport-Security` (in production/HTTPS), and a CSP
tuned to NiceGUI's asset/websocket needs. Also confirm the NiceGUI session cookie carries
`HttpOnly`, `SameSite`, and (in production) `Secure`.

**Fixed.** Added `middleware/security_headers.py` (`SecurityHeadersMiddleware`, registered in
`main.py`) setting `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, CSP
`frame-ancestors 'none'`, `Referrer-Policy: strict-origin-when-cross-origin`, and (in
production) HSTS. A full script/style CSP is intentionally omitted because NiceGUI/Quasar
rely on inline assets; tuning one is left as a follow-up to verify against a running
instance. Reviewing the NiceGUI session-cookie flags remains a recommended manual check.

### 5. Production image ships dev dependencies — Low / Info

**Location:** `Dockerfile`

`poetry install` is run without `--only main`, so test/dev tools (pytest, ipython, …) land
in the runtime image, enlarging it and the attack surface slightly.

**Remediation.** Use `poetry install --only main --no-root` (or equivalent) for the runtime
image.

**Fixed.** The `Dockerfile` now runs `poetry install --only main`.

### 6. No `SECURITY.md` / dependency scanning — Info

There is no documented vulnerability-disclosure path and no automated dependency
vulnerability scan in CI. Dependencies were current at audit time (FastAPI 0.136,
NiceGUI 3.12, Tortoise 0.24, cryptography 48, aiohttp 3.14, Jinja2 3.1.6).

**Remediation.** Add a `SECURITY.md` (reporting/disclosure policy) and a scheduled
`pip-audit` (or Dependabot) job in CI to catch newly disclosed CVEs.

**Fixed.** Added `SECURITY.md` (disclosure policy + supported configuration) and
`.github/workflows/security.yml`, which runs `pip-audit` on push/PR, weekly, and on demand.

---

## Notable strengths

- Single service-layer authorization choke point; every REST mutation passes `actor` to a
  service that enforces role/ownership checks (`ServiceErrorRoute` maps `PermissionError`
  → 403, `ValueError` → 400).
- Fail-fast startup config validation (`application/utils/environment.py`): missing
  `STORAGE_SECRET` aborts in every environment; production additionally requires a
  ≥32-char secret and DB credentials, and refuses `MOCK_DISCORD`/`MOCK_CHALLONGE`.
- Strict input validation on the highest-risk free-text field (triforce text lines:
  19-char, character-allowlist regex).
- Comprehensive audit logging of sensitive create/update/delete actions.
- Non-root container (`uid 10001`), Postgres not published outside the compose network,
  single-worker by design.

## Suggested remediation order

1. Finding #1 (stored XSS) — sanitize/relayout the markdown render.
2. Finding #4 (security headers, incl. CSP) — also hardens #1.
3. Finding #2 (tighten `require_staff` on the two routes).
4. Finding #3 (proxy-aware rate-limit key).
5. Findings #5–#6 (build/CI hygiene).
