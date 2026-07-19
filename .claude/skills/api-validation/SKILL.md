---
name: api-validation
description: >-
  Validate REST API changes against the real running app — boots the server,
  seeds two tenants, and drives endpoints with curl using deterministic seeded
  bearer tokens. The API counterpart of /ui-validation: pytest covers routers
  in-process via ASGITransport, but only this exercises the live stack
  (middleware, rate limiting, token→tenant resolution) end to end. Use after
  adding or changing api/ routers/schemas, or when asked to verify an endpoint
  against the real app.
---

# Validating the REST API against the running app

## Setup and boot (same flow as /ui-validation)

One-time per environment: `bash scripts/setup_env.sh` (Postgres 16, tzdata,
deps, dev `.env` with `MOCK_DISCORD=true`).

Each run:

```bash
nohup ./start.sh dev > /tmp/app.log 2>&1 &
# wait for "Application startup complete" in /tmp/app.log
poetry run python scripts/seed_dev.py
```

## Auth: deterministic seeded tokens

The seed creates two bearer tokens **per tenant** (slugs `default` and
`second` — see `scripts/seed_dev.py`, "Dev Seed Token"):

| Token | Access |
|---|---|
| `wizzrobe_pat_devseed_<slug>_local_only_do_not_use` | staff, read-write |
| `wizzrobe_pat_devseedro_<slug>_local_only_do_not` | read-only |

Base URL is `http://127.0.0.1:8000/api` — **no `/t/<slug>` prefix**: the API
is excluded from `TenantMiddleware` and derives its tenant from the token
(`api/dependencies.py::resolve_token`). Same-shaped calls under different
tokens are how you probe tenant behavior.

```bash
RW="Authorization: Bearer wizzrobe_pat_devseed_default_local_only_do_not_use"
RO="Authorization: Bearer wizzrobe_pat_devseedro_default_local_only_do_not"
B="Authorization: Bearer wizzrobe_pat_devseed_second_local_only_do_not_use"

curl -s -H "$RW" http://127.0.0.1:8000/api/matches | python3 -m json.tool
```

## Per-endpoint checklist

For each new/changed endpoint, verify with curl (`-s -o /dev/null -w '%{http_code}'`
for status-only probes):

1. **401** with no `Authorization` header.
2. **403** on writes with the read-only token (and with a token lacking the
   required role, if the endpoint is role-gated).
3. **404** for a bogus id — must be 404, not 400: proves the service raises
   `NotFoundError` and no router preload crept back in.
4. **Cross-tenant 404**: request a `default`-tenant row's id with the
   `second` token. This is the live leak check — anything but 404 is a
   tenant-isolation bug.
5. **Response shape** matches the `api/schemas/` model (diff the JSON keys);
   list endpoints paginate or bound their size where the collection is
   high-cardinality.
6. Note the rate limiter (`api/rate_limit.py`) when hammering an endpoint in
   a loop — spread calls or expect 429s.

## Wrap up

- New/changed endpoints are documented in
  [docs/reference/rest-api.md](../../../docs/reference/rest-api.md)
  (doc-check will remind you).
- The in-process equivalents live in `tests/test_api_*.py` — anything you
  verified by hand here that isn't covered there should become a test
  (`tests/api_helpers.py` + the conftest `app`/`two_tenant_api` fixtures).
- Kill the server when done: `pkill -f 'start.sh dev' ; pkill -f uvicorn`.
