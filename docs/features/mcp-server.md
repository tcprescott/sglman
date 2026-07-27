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
`WWW-Authenticate: Bearer resource_metadata="…"`, not 403. 403 would be accurate
but leaves the client with nowhere to go; the 401 plus the challenge is what
lets a compliant client discover the authorization server and start the flow.

The refusal is mutual: an OAuth token presented to `/api` is refused too. A
credential minted for one surface can never be replayed against the other.

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
`@protected_page`. Every `@protected_page` is a *tenant* page and 404s when
reached without a tenant, but an MCP grant is deliberately platform-wide — it
authenticates a person, not a membership. It registers itself in
`protected_routes` directly to get the sign-in redirect.

There is **no community picker**. The token carries no community; asking would
imply a scoping it does not have.

It still reads as Wizzrobe: the page applies
[`render_platform_chrome('Authorize')`](../reference/frontend.md#tenant-less-chrome-themechromepy)
— the shared tenant-less header, stylesheet, phoenix palette and dark mode — and
its card, grant list and expired-transaction notice use the `.consent-*` classes
in `styles.css`. The palette is the shipped default rather than a tenant
override, because the credential being granted is not scoped to a community.

## Choosing a community

Every tool except `whoami` and `list_tenants` takes a required `tenant` argument
— a community slug. `list_tenants` returns the slugs the caller may use.

**Membership floor.** A tool reaches a community only where its user actually
holds a role (super admins excepted). This is not decoration: a REST token is
bound to one community and can never address another, so without the floor an
`ACTOR`-gated tool would let any signed-in user read every other community's
tournaments and schedule. The floor restores parity with the REST surface.

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
subsystem the community has not enabled is hidden from everyone, staff included.
A `forbidden` there would confirm the feature exists.

**Read-only tokens are never rejected.** Every OAuth token is minted
`read_only=True` because the surface performs no writes, so a rejection would
refuse every legitimate caller. If a write tool is ever added it needs its own
explicit check — do not restore a blanket one.

## Tool catalogue

`tenant` is required on every tool below except the two orientation tools.

### Orientation
| Tool | Gate | Notes |
|---|---|---|
| `whoami` | GLOBAL | Identity, plus roles per community. The cheapest way to orient. |
| `list_tenants` | GLOBAL | The slugs every other tool needs. |

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
| `list_users` | STAFF | — |
| `list_match_crew`, `crew_coverage_report` | ADMIN | — |
| `list_volunteer_shifts`, `volunteer_coverage` | ADMIN | `VOLUNTEERS` |

The volunteer tools sit one gate **above** their REST counterparts
(`require_api_actor`). Deliberate: the REST reads back a self-service view of
your own shift, whereas one call here returns a whole window's roster with names.

`list_match_crew` includes **unapproved** signups, which is why it is ADMIN while
`get_match` is ACTOR — `get_match` reuses the REST serializer and inherits its
rule that unapproved crew are never disclosed.

### Observability
| Tool | Gate |
|---|---|
| `list_audit_log` | ADMIN |
| `telemetry_summary`, `telemetry_top`, `get_system_config` | STAFF |

### Feature-gated competition
| Tool | Gate | Flag |
|---|---|---|
| `list_brackets`, `get_bracket_standings` | ACTOR | `BRACKETS` |
| `list_async_qualifiers` | ACTOR | `ASYNC_QUALIFIERS` |

## Response shapes

Two rules, in `mcpserver/schemas.py`:

- **Singular reads reuse the REST model.** `get_match` goes through
  `api/_match_view.serialize_match`, so rules baked into it cannot drift between
  the two surfaces.
- **List reads get a compact shape.** A hundred full match records is mostly
  padding, and padding is the expensive kind of wrong for an LLM consumer: it
  buries the answer and burns the context the model needs to reason.

All datetimes are UTC as stored. Users see US/Eastern; the model is told once in
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

Three settings in `mcpserver/server.py` are load-bearing and non-obvious. Each is
pinned by a test.

- **`stateless_http=True` is a correctness requirement, not a scaling knob.** In
  stateful mode the MCP server task is spawned once per *session* and snapshots
  the context of whichever request created it, so a second token on that session
  would execute as the first user. Stateless spawns a task per HTTP request,
  which inherits that request's actor.
- **`json_response=True`** — the app's `BaseHTTPMiddleware` stack wraps `/mcp`,
  and `BaseHTTPMiddleware` around long-lived SSE is a known source of hangs on
  client disconnect.
- **DNS-rebinding protection is off explicitly.** It auto-enables when the
  configured host is loopback (the default) and would 421 every production
  request — failing in exactly the environment local testing cannot reveal.

Two more, elsewhere:

- **A `Route`, not a `Mount`.** Starlette compiles a mount to
  `^/mcp/(?P<path>.*)$`, so bare `POST /mcp` — what every client sends — would
  only reach it via a 307, and clients do not follow redirects by default.
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

- `tests/mcp/` — transport, catalogue guardrails, the authorization matrix, and
  the full OAuth flow. The harness is `tests/mcp/conftest.py::mcp_session`, an
  async context manager used **inside** the test body: the session manager is
  single-use per instance and is an anyio cancel scope, which must be exited in
  the task that entered it, so a `yield`-style fixture cannot work.
- `tests/tenancy/test_mcp_tenant_isolation.py` — scoping plus context hygiene.
  The interleaving test is the one a single-call test cannot make: a binding set
  without a matching reset passes every one-call-at-a-time test and fails there,
  which is also how it would fail in production.

Dev fixtures: `scripts/seed_dev.py` seeds a registered client and a deterministic
OAuth bearer (`wizzrobe_mcp_devseed_local_only_do_not_use`) so `/mcp` can be
driven with curl without the browser flow.
