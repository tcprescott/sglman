# MCP server

Wizzrobe serves a remote **MCP** (Model Context Protocol) endpoint at `/mcp`, so
organizers can connect Claude Desktop or Claude Code to their communities and
ask questions across tournaments, matches, people, and history.

The surface is **OAuth-only**, and **read-only unless the person connecting asks
otherwise**. It is a fourth entry surface alongside the web UI, the REST API, and
the Discord bot: it calls services, never repositories, and holds no business
logic of its own.

| | |
|---|---|
| Endpoint | `POST/GET/DELETE {BASE_URL}/mcp` |
| Transport | Streamable HTTP, **stateless**, JSON responses (no SSE on POST) |
| Auth | OAuth 2.1 (RFC 7591 dynamic registration + PKCE). **Personal access tokens are refused.** |
| Writes | 19 match-management tools, served only to a connection the consent screen approved for writing. Everything else is a read annotated `readOnlyHint`. |
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
access. Rotation re-keys the same row, so `scope` and `read_only` survive it —
a refresh can never widen a grant.

### Scopes

| Scope | Granted | Effect |
|---|---|---|
| `wizzrobe:read` | always | The read tools. |
| `wizzrobe:write` | only when the consent box is ticked | The write tools, and `read_only=False` on the token. |

A dynamically-registered client is registered with **both**, so a client that
asks for write is not rejected at `/authorize` — but asking is not getting.
`McpAuthService.granted_scope` derives the granted scope from the human's answer
alone and ignores what the client requested, which is what keeps the box on the
consent screen from being decoration.

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

**The write box.** One unticked checkbox, "Let it make changes". It is the only
place write access can be granted: a client cannot request its way past it and a
refresh cannot widen a grant without it, so raising a read-only connection to a
writing one means reconnecting. Ticking it redraws the grant list — the two
write lines appear and the closing note flips from "it cannot change anything" to
"it acts as you" — because a card that lists writes while still promising
read-only is worse than either half alone. The connection's kind is visible
afterwards on the profile's credential list, where a writing grant carries a
`can make changes` badge and a read-only one carries none.

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

**The read-only refusal is per tool, never per connection.** Read-only is the
consent screen's default and most connections carry it, so the REST API's shape
— reject the token outright — would refuse nearly every legitimate caller here.
`authorize()` instead refuses only the tools registered `write=True`, and only
after the feature and membership checks have run, so a read-only token learns no
more about a community than a writing one would.

Order within `authorize()`, and why: **feature → membership floor → connection →
role**. The connection check sits below the membership floor because a
`forbidden: read-only` for a community the user cannot see would disclose that
the community exists. It sits above the role check because the two refusals
call for different fixes — reconnect with the box ticked, versus ask someone for
a role — and the connection one is both cheaper and the common case.

## Tool catalogue

`tenant` is required on every tool below except the two orientation tools.

### Orientation
| Tool | Gate | Notes |
|---|---|---|
| `whoami` | GLOBAL | Identity, roles, enabled flags per community, **and `can_write`**. The cheapest way to orient. |
| `list_tenants` | GLOBAL | The slugs every other tool needs, with the same roles/flags. |

Both report each community's live feature flags. A flag is not a permission, so
it goes to everyone who can see the community — and reporting it lets a client
skip a tool instead of discovering its `not_found` a round-trip later.
`can_write` is a property of the *connection*, not the person: the same user can
hold a writing grant in one client and a reading one in another.

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

## Writes

Nineteen tools in [`mcpserver/tools/match_writes.py`](../../mcpserver/tools/match_writes.py),
served only to a connection approved for writing.

**Scope, and the rule that fixes it.** The write surface is exactly what
`api/routers/match_actions.py` exposes, tool for tool. That is worth stating
because the alternative — adding whichever writes seem useful — leaves two
surfaces that drift and no answer for the next proposal. A write that belongs
here belongs in the REST router too, and the reverse.

| Group | Tools |
|---|---|
| Scheduling | `create_match`, `submit_match_request`, `update_match`, `delete_match` |
| Stream and stations | `set_match_stream_candidate`, `assign_match_stream_room`, `assign_match_stations` |
| Lifecycle | `seat_match`, `start_match`, `finish_match`, `confirm_match`, `record_match_result`, `set_match_review`, `generate_match_seed` |
| Your own participation | `signup_as_crew`, `withdraw_crew_signup`, `acknowledge_match`, `watch_match`, `unwatch_match` |

Every one is registered at **ACTOR**, mirroring `require_write_actor`: holding a
live token approved for writing is the bar at this layer, and the real check is
the service's own (`can_crud_match`, `can_run_match`, `can_confirm_match`,
`can_assign_match_stream`). A stricter gate here would make the two surfaces
answer differently for the same person, and the service check is the one that
knows about tournament admins. A writing grant is **not a promotion** — the token
still acts as its user.

`delete_match` and `withdraw_crew_signup` are additionally annotated
`destructiveHint`, which is how a client decides how hard to ask before
proceeding.

### Hiding writes from a read-only listing

`WizzrobeMCP.list_tools` (in `mcpserver/server.py`) filters the write tools out
for a read-only connection. It is **not** the security boundary — the gate is,
and `test_mcp_writes.py` calls every write tool over the wire with a read-only
token to prove it. It is a context boundary: a read-only client offered nineteen
tools it can never call spends tokens on their schemas and plans work it cannot
do, with the refusal arriving a round-trip after the model has told the user it
would reschedule their match.

The listing runs inside the request's context (see `mcpserver/asgi.py`), so the
actor is the one whose token is being served. Outside a request — the SDK builds
the list once while wiring itself up — `optional_actor()` returns `None` and the
full catalogue is returned.

## Response shapes

Two rules, in `mcpserver/schemas.py`:

- **Singular reads reuse the REST model.** `get_match` goes through
  `api/_match_view.serialize_match`, so rules baked into it cannot drift between
  the two surfaces. Writes follow the same rule and return the same
  `MatchResponse`, so the model reads back exactly what it changed; the four
  that have no record to hand back return `OperationResult`.
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
- `tests/mcp/test_mcp_writes.py` — the write surface in three layers: the
  connection gate (every write tool called over the wire with a read-only
  token), the role gate underneath it, and whether the writes actually land.
  Plus the consent decision itself — the box unticked mints a read-only token, a
  client that requests write without it still gets one, and a refresh cannot
  widen the grant.
- `tests/tenancy/test_mcp_tenant_isolation.py` — scoping plus context hygiene.
  Its interleaving test catches what a single-call test cannot: a binding set
  without a matching reset passes every one-call-at-a-time test.

Dev fixtures: `scripts/seed_dev.py` seeds a registered client and **two**
deterministic OAuth bearers so `/mcp` can be driven with curl without the browser
flow — `wizzrobe_mcp_devseed_local_only_do_not_use` (read-only) and
`wizzrobe_mcp_devseedwrite_local_only_do_not_use` (writing). Two, because the
surface a token is served depends on the consent decision behind it; one would
leave half the server unreachable from a dev loop.
