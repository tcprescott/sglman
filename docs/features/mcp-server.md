# MCP server

Wizzrobe serves a remote **MCP** (Model Context Protocol) endpoint at `/mcp`, so
organizers can connect Claude Desktop or Claude Code to their communities and
ask questions across tournaments, matches, people, and history.

The surface is **read-only** and **OAuth-only**. It is a fourth entry surface
alongside the web UI, the REST API, and the Discord bot: it calls services, never
repositories, and holds no business logic of its own.

| | |
|---|---|
| Endpoint | `POST/GET/DELETE {BASE_URL}/mcp` |
| Transport | Streamable HTTP, **stateless**, JSON responses (no SSE on POST) |
| Auth | OAuth 2.1 (RFC 7591 dynamic registration + PKCE). **Personal access tokens are refused.** |
| Writes | None. Every tool is a read and is annotated `readOnlyHint`. |
| Feature flag | None — the server is always on. `MCP_ENABLED=false` is an operational kill switch. |
| Rate limit | Shares `/api`'s buckets and `API_RATE_LIMIT_PER_MIN` (default 120). |
| Code | [`mcpserver/`](../../mcpserver), consent page [`pages/mcp_consent.py`](../../pages/mcp_consent.py) |

## Connecting a client

**Claude Desktop** — Settings → Connectors → Add custom connector, URL
`https://<your-host>/mcp`. It discovers the authorization server, opens a browser
to sign in with Discord, and shows a consent screen.

**Claude Code** — `claude mcp add --transport http wizzrobe https://<your-host>/mcp`,
then `/mcp` to complete the browser flow.

**MCP Inspector** — `npx @modelcontextprotocol/inspector` against the same URL;
the fastest way to see every tool's schema and drive the OAuth flow by hand.

Users find the URL on their profile page, under **API tokens & AI clients**, and
disconnect a client from the same list.

## Authentication

### Why not personal access tokens

A PAT presented to `/mcp` gets **401** with
`WWW-Authenticate: Bearer resource_metadata="…"`, not 403 — the challenge is what
lets a compliant client discover the authorization server and start the flow,
where an accurate 403 would leave it nowhere to go. The refusal is mutual: an
OAuth token presented to `/api` is refused too, so a credential minted for one
surface can never be replayed against the other.

### The two token kinds

Both live in `ApiToken`, distinguished by `origin` — one table so revocation,
expiry, and the profile listing have a single implementation.

| `origin` | `tenant` | Surface | Scope |
|---|---|---|---|
| `pat` | set | `/api` | one community, unchanged from before |
| `oauth` | `NULL` | `/mcp` | platform-wide; each tool call names its community |

OAuth access tokens live 1 hour and carry a 30-day refresh token. Refreshing
rotates **both** halves, so a leaked refresh token is single-use: the theft
surfaces as the attacker's next call failing rather than as silent parallel
access.

### Discovery

- `/.well-known/oauth-protected-resource` (and the `/mcp`-suffixed form) — RFC 9728.
- `/.well-known/oauth-authorization-server` — RFC 8414, from the MCP SDK.

Both are served at the **origin root** and need no credential. The SDK's helper
would register them inside the FastMCP sub-app, where no client looks, so
`mcpserver/wellknown.py` registers them on the outer app instead.

### Consent

`pages/mcp_consent.py` at `/oauth/mcp/consent` is a bespoke `@ui.page`, not a
`@protected_page`: every `@protected_page` is a *tenant* page and 404s without a
tenant, but an MCP grant is platform-wide — it authenticates a person, not a
membership. It registers itself in `protected_routes` directly to get the
sign-in redirect. There is **no community picker**; the token carries no
community, so asking would imply a scoping it does not have.

It still reads as Wizzrobe: the page applies
[`render_platform_chrome('Authorize')`](../reference/frontend.md#tenant-less-chrome-themechromepy)
— the shared tenant-less header, stylesheet, phoenix palette and dark mode — and
its card, grant list and expired-transaction notice use the `.consent-*` classes
in `styles.css`. The palette is the shipped default, not a tenant override,
because the credential is not scoped to a community.

## Choosing a community

Every tool except `whoami` and `list_tenants` takes a required `tenant` argument
— a community slug. `list_tenants` returns the slugs the caller may use.

**Membership floor.** A tool reaches a community only where its user actually
holds a role (super admins excepted) — parity with the REST surface, where a
token is bound to one community and can never address another.

An unknown slug and an entitled-elsewhere slug produce **byte-identical**
`not_found` errors, so error text cannot be diffed into a directory of the
communities hosted here.

## Authorization

Each tool mirrors the gate its REST counterpart uses. `mcpserver/registry.register`
is the only way to attach a tool to the server, so none can ship ungated —
`tests/mcp/test_mcp_catalogue.py` asserts the served list and the gate registry
agree.

| Gate | Requirement | REST equivalent |
|---|---|---|
| `GLOBAL` | a live token; names no community | — |
| `ACTOR` | a live token + a role in the named community | `require_api_actor` |
| `STAFF` | `AuthService.is_staff` | `require_staff` |
| `ADMIN` | `AuthService.can_view_admin` | `require_admin` |

The feature flag is checked **before** the role, matching `@protected_page`: a
subsystem the community has not enabled is hidden from everyone, staff included,
and answers `not_found` — a `forbidden` would confirm the feature exists.

**Read-only tokens are never rejected.** Every OAuth token is minted
`read_only=True` because the surface performs no writes, so a blanket rejection
would refuse every legitimate caller. A write tool, if ever added, needs its own
explicit check.

## Tool catalogue

`tenant` is required on every tool below except the two orientation tools.

### Orientation
| Tool | Gate | Notes |
|---|---|---|
| `whoami` | GLOBAL | Identity, roles **and enabled flags** per community. The cheapest way to orient. |
| `list_tenants` | GLOBAL | The slugs every other tool needs, with the same roles/flags. |

Both report each community's live feature flags. A flag is not a permission, so
it goes to everyone who can see the community — and reporting it lets a client
skip a tool instead of discovering its `not_found` a round-trip later.

### Tournaments and matches
| Tool | Gate | Flag |
|---|---|---|
| `list_tournaments`, `get_tournament`, `list_stream_rooms` | ACTOR | — |
| `list_matches`, `get_match`, `get_schedule` | ACTOR | — |
| `match_operations_report` | ADMIN | — |

### People, crew, volunteers
| Tool | Gate | Flag |
|---|---|---|
| `get_user` | ACTOR (self, or staff for anyone else) | — |
| `get_player_availability` | ACTOR (self, or staff for anyone else) | — |
| `list_users` | STAFF | — |
| `list_match_crew`, `crew_coverage_report` | ADMIN | — |
| `list_volunteer_shifts`, `volunteer_coverage`, `volunteer_hour_trends` | ADMIN | `VOLUNTEERS` |

The volunteer tools sit one gate **above** their REST counterparts
(`require_api_actor`), deliberately: REST reads back a self-service view of your
own shift, whereas one call here returns a whole window's roster with names.
`volunteer_hour_trends` is served by `AnalyticsService`, which carries no flag of
its own, so `VOLUNTEERS` is declared at the tool — without it a community with
volunteers off could still read its volunteer hours here.

`list_match_crew` includes **unapproved** signups, which is why it is ADMIN while
`get_match` is ACTOR — `get_match` reuses the REST serializer and inherits its
rule that unapproved crew are never disclosed.

### Reports
| Tool | Gate |
|---|---|
| `capacity_forecast`, `stream_room_utilization` | ADMIN |
| `tournament_health`, `crew_participation_trends`, `activity_trends` | ADMIN |
| `matches_active_at` | ADMIN |

ADMIN mirrors the Admin → Reports tab (`is_staff or tournament-admin or
crew-coordinator`, which is what `can_view_admin` answers).

Two are **reshaped rather than passed through**, because `ReportsService` builds
its payloads for a chart (per-interval and per-match detail; `stream_room_utilization`'s
even contains ORM `Match` rows): `capacity_forecast` returns peaks and headroom
instead of the full series, `stream_room_utilization` per-room totals instead of
every booking.

### Equipment
| Tool | Gate | Flag |
|---|---|---|
| `list_equipment`, `get_equipment` | ADMIN | `EQUIPMENT` |

No REST counterpart exists, so the gate of record is the Admin → Equipment tab
(`is_staff or is_equipment_manager` — both satisfy `can_view_admin`).
`private_notes` is deliberately not returned.

### Observability
| Tool | Gate |
|---|---|
| `list_audit_log` | ADMIN |
| `telemetry_summary`, `telemetry_top`, `get_system_config` | STAFF |
| `list_service_health`, `list_webhooks`, `list_webhook_deliveries` | STAFF |
| `list_feedback` | STAFF |

`list_webhooks` never returns the signing secret, and `list_service_health` is
the **tenant subset** only — the platform-wide board is a super-admin surface and
is not exposed here.

### Online play
| Tool | Gate | Flag |
|---|---|---|
| `list_presets`, `get_preset` | ACTOR | — |
| `list_race_room_profiles`, `get_race_room` | ACTOR | `RACETIME_ROOMS` |
| `list_race_rooms` | STAFF | `RACETIME_ROOMS` |
| `list_speedgaming_links`, `list_speedgaming_episodes` | ACTOR | `SPEEDGAMING_ETL` |

Several sit at ACTOR because the *service* carries the real check
(`can_manage_presets`, `ensure_can_manage_sync`); mirroring the router's gate
rather than inventing a stricter one keeps both surfaces answering the same
question. `list_race_rooms` is the exception at STAFF, matching
`GET /race-rooms/open`, whose service read has no gate of its own.

### Feature-gated competition
| Tool | Gate | Flag |
|---|---|---|
| `list_brackets`, `get_bracket`, `list_bracket_matches` | ACTOR | `BRACKETS` |
| `list_bracket_entrants`, `get_bracket_standings` | ACTOR | `BRACKETS` |
| `list_async_qualifiers`, `get_async_qualifier` | ACTOR | `ASYNC_QUALIFIERS` |
| `get_async_qualifier_leaderboard` | ACTOR | `ASYNC_QUALIFIERS` |
| `list_async_qualifier_live_races` | ACTOR | `ASYNC_QUALIFIERS` |

`list_bracket_matches` resolves entry ids to entrant names from two list reads
rather than prefetching per match: a fixed pair of queries covers the whole
field, whatever its size.

## Response shapes

Two rules, in `mcpserver/schemas.py`:

- **Singular reads reuse the REST model.** `get_match` goes through
  `api/_match_view.serialize_match`, so rules baked into it cannot drift between
  the two surfaces.
- **List reads get a compact shape.** A hundred full match records is mostly
  padding, which buries the answer and burns the model's context.

A third rule is about the *annotation*, and it fails silently: **never return a
bare `dict`**. `func_metadata` derives the output schema from the return type,
and `dict` yields **no schema at all** — the SDK then sends the payload as a JSON
string in a text block instead of `structuredContent`, while a `Dict[str, Any]`
tool right beside it returns a properly typed result. Nothing in the tool's
source shows the difference, so
`test_mcp_catalogue.py::test_every_tool_declares_an_output_schema` asserts it.

Where a service payload is built for a chart rather than a reader, the tool
reshapes it — see the reports section above. `mcpserver/tools/_args.py` holds the
shared timestamp/limit parsing so every tool refuses a bad window in the same
words.

All datetimes are UTC as stored. Each community chooses the zone its members read them in; the model is told once in
the server instructions rather than per field.

## Errors

`Tool.run` in the SDK catches every exception and re-raises a bare `ToolError`,
so the type is gone above the tool. Mapping therefore happens inside the
per-tool wrapper (`mcpserver/errors.py`), not at a central seam. Ordering mirrors
`ServiceErrorRoute`, including `NotFoundError` before `ValueError` (it subclasses
it):

| Exception | Tool error |
|---|---|
| `PermissionError` | `forbidden: …` |
| `NotFoundError` (incl. `FeatureDisabledError`) | `not_found: …` |
| `ValueError` | `invalid_request: …` |
| anything else | `internal_error: …` (logged with traceback → Sentry; opaque to the model) |

The prefixes are machine-readable on purpose: they let the model tell "I lack
permission, tell the user" from "wrong id, list first" without parsing English.

Transport failures are HTTP-level and OAuth-shaped: **401** missing/invalid/
non-OAuth token, **403** deactivated account, **405** wrong method, **406** bad
`Accept`, **429** rate limited.

## Implementation notes

Four settings in `mcpserver/server.py` are load-bearing and non-obvious. Each is
pinned by a test.

- **`stateless_http=True` is a correctness requirement, not a scaling knob.** In
  stateful mode the MCP server task is spawned once per *session* and snapshots
  the context of whichever request created it, so a second token on that session
  would execute as the first user. Stateless spawns a task per HTTP request,
  which inherits that request's actor.
- **`json_response=True`** — the app's `BaseHTTPMiddleware` stack wraps `/mcp`,
  and `BaseHTTPMiddleware` around long-lived SSE is a known source of hangs on
  client disconnect.
- **`streamable_http_path='/'`** — the path is served from
  `mcpserver/__init__.py`; the SDK default would nest the real endpoint at
  `/mcp/mcp`.
- **DNS-rebinding protection is off explicitly.** It auto-enables when the
  configured host is loopback (the default) and would 421 every production
  request — failing in exactly the environment local testing cannot reveal.

Two more, elsewhere:

- **A `Route`, not a `Mount`.** Starlette compiles a mount to
  `^/mcp/(?P<path>.*)$`, so bare `POST /mcp` — what every client sends — would
  only reach it via a 307, and clients do not follow redirects by default. This
  is why `streamable_http_path` is `'/'`.
- **`mcpserver.mount(app)` must run before `frontend.init(app)`** in `main.py`.
  NiceGUI mounts itself at `/` and would swallow `/mcp`.

`FastMCP.__init__` calls `logging.basicConfig`, so the server is built inside
`mount()` rather than at import time — otherwise it wins the race against
`main.py`'s own logging setup and strips the format process-wide.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MCP_ENABLED` | on | Kill switch. When off there is no `/mcp` route, no discovery routes, and the lifespan hook is a no-op. |
| `BASE_URL` | `http://localhost:8000` | The resource identifier (`{BASE_URL}/mcp`) and the OAuth issuer. Must be the public URL. |
| `API_RATE_LIMIT_PER_MIN` | 120 | Shared with `/api`. |

A reverse proxy must pass `/mcp` and `/.well-known/*` through unrewritten.
`FASTMCP_*` environment variables are inert — constructor arguments outrank them
in pydantic-settings.

## Testing

- `tests/mcp/` — transport, catalogue guardrails, the authorization matrix, the
  full OAuth flow, and `test_mcp_reads.py`, which calls every read tool against
  seeded rows (the catalogue tests prove a tool is *served* and *gated* but never
  run it, so a compact shape reading a renamed relation or an un-prefetched FK
  would ship green). The harness is `tests/mcp/conftest.py::mcp_session`, an
  async context manager used **inside** the test body: the session manager is
  single-use per instance and is an anyio cancel scope, which must be exited in
  the task that entered it, so a `yield`-style fixture cannot work.
- `tests/tenancy/test_mcp_tenant_isolation.py` — scoping plus context hygiene.
  Its interleaving test catches what a single-call test cannot: a binding set
  without a matching reset passes every one-call-at-a-time test.

Dev fixtures: `scripts/seed_dev.py` seeds a registered client and a deterministic
OAuth bearer (`wizzrobe_mcp_devseed_local_only_do_not_use`) so `/mcp` can be
driven with curl without the browser flow.
