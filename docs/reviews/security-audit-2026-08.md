# Security audit — the week to 2026-08-03

Scope: every commit since `bc7ebeb` (2026-07-27), which is 328 commits and 835
files — the room-token kiosk view, the MCP write surface and its OAuth
authorization server, the cross-host login handoff, web push, reschedule
requests, payouts, equipment self-checkout, the static spectator brackets, and
the new REST routers behind all of them.

Method: read every entry surface that authenticates, authorizes, renders
attacker-controlled text, or makes an outbound request; trace each to the
service gate behind it. Full suite green (5405 passed), `ruff` clean, mypy
ratchet at baseline.

## What was fixed here

### 1. The MCP consent screen named the client but not where the code went — medium

`pages/mcp_consent.py` rendered `"{client_name} wants to access Wizzrobe as
{you}"` and nothing else identifying. Client registration is open by design
(RFC 7591 is what lets a client configure itself from a URL), and
`McpAuthService.register_client` accepts any `client_name` with any
`redirect_uris`. So the sequence was:

1. Attacker POSTs `/register` with `client_name: "Claude"` and
   `redirect_uris: ["https://claude.ai.evil.test/cb"]`.
2. Victim opens the attacker's `/authorize` link, signs in, sees a Wizzrobe-
   branded card that says Claude wants access as them, and approves.
3. The code lands on the attacker's host. Exchanged, it is a token acting as the
   victim — and if they ticked the write box, a writing one.

Nothing downstream catches this: PKCE binds the code to the client that started
the flow, which is the attacker, and the redirect-URI consistency check compares
authorize against token, both attacker-supplied. The consent screen was the only
place a human could have noticed, and it withheld the one field that cannot be
faked.

Fixed by putting the redirect target on the card, under the lede, with the
reason it matters: *"Approving sends your access to `claude.ai.evil.test`. Any
app can call itself anything here, so check that address is the one you started
from."* `_redirect_target()` shows host and port for `http(s)` and the whole URI
for a native client's custom scheme (`cursor://…` has no netloc).

### 2. The unauthenticated OAuth routes had no rate limit — low

`register_oauth_routes` appends the SDK's four authorization-server routes to
the **outer** FastAPI app so clients find them at the origin root. That places
them outside both existing limiters: `api/__init__.py` attaches `rate_limit` to
the `/api` router, and `mcpserver/asgi.py` calls it for `/mcp`. Nothing covered
`/register`, `/token`, `/authorize` or `/revoke`.

`/register` is the sharp one — unauthenticated, open by design, and one INSERT
into `mcp_oauth_clients` per call, so table growth was bounded only by how fast
someone could POST. `/token` was an unmetered oracle for guessing at a code or
refresh token (both 32 bytes of `secrets`, so not practically guessable — but
"not guessable" is a poor reason to leave the door unmetered).

Fixed by wrapping each route's ASGI app with the shared limiter, so a client is
throttled on one budget across `/api`, `/mcp` and the AS routes rather than
three independent ones. Wrapped at the ASGI layer because the routes are not one
shape: the SDK hands `/authorize` a plain request handler and wraps the other
three in `CORSMiddleware`. `OPTIONS` passes through — a 429 on a preflight
breaks a browser client (MCP Inspector) for a reason it cannot report.

## Open, not fixed here

### `GET /api/users/{id}` reads across communities — low/medium, needs a product call

`api/routers/users.py` gates the route on "self, or Staff", then loads the user
globally: `load_user_or_404` → `UserService.get_user_by_id`, no tenant filter.
The MCP `get_user` tool (`mcpserver/tools/people.py`) does the same. So STAFF of
any community can walk `id=1..N` and read every account on the platform:
username, `discord_id`, display name, pronouns, active flag.

What makes this worth raising is that the sibling endpoint was already fixed —
`list_users` carries the comment *"returning the platform's whole user table was
a leak; there is deliberately no `?scope=all`, which would re-open it behind a
parameter."* The by-id route re-opens it behind a loop.

Not fixed unilaterally because scoping it is a real behaviour change and the
codebase argues both ways. `CLAUDE.md` says identity is global; the equipment
borrower picker deliberately widens past members because *"lending to someone who
just walked into the venue is the case this serves"*. The narrow fix — resolve
only users who hold a role or membership in the actor's tenant, with the actor
and super-admins exempt — would break that flow unless the picker keeps its own
path. Worth a decision rather than a patch.

## Checked and sound

Recorded so the next audit does not re-derive them.

- **Room tokens** (`RoomTokenService`, `pages/room_seeds.py`). SHA-256 stored,
  raw value shown once, `secrets.token_urlsafe(32)`. `get_by_hash` is tenant-
  scoped, so a wrong-community token falls out of the query. Unknown, revoked,
  malformed and wrong-community all render the same 404. The token rides in the
  URL, but `_SECRET_PARAM_MARKERS` in `middleware/auth.py` redacts it out of
  telemetry, and `Referrer-Policy: strict-origin-when-cross-origin` keeps it out
  of the `Referer` when a kiosk user clicks through to a seed host.
- **The cross-host login handoff** (`oauth_handoff_service`). Single-use nonce,
  30s TTL, host signed into the token *and* held in the store *and* compared
  against where it was presented, and a browser-binding commitment that stops a
  token minted in one browser being delivered to another. `/oauth/start`
  allow-lists the target against active tenant domains.
- **MCP tenant isolation.** `registry.register` binds `tenant_scope` around every
  tool and authorizes inside it; `mcpserver/auth.authorize` applies a membership
  floor before any gate, wording the refusal identically to an unknown slug so
  error text is not a directory of communities. Refresh re-keys the same row, so
  a grant can never widen without going back through consent.
- **REST authorization.** Every router's dependency matches its documented gate;
  the two unauthenticated routes (`/health`, `/web-push/rotate`) are deliberate
  and both are inside the rate-limited router. `resolve_token` refuses an OAuth
  token at `/api` and `asgi.py` refuses a PAT at `/mcp`, so neither surface's
  credential replays against the other.
- **Web-push rotation.** Unauthenticated by necessity (a
  `pushsubscriptionchange` handler has no session), authenticated instead by
  `hmac.compare_digest` against the retired subscription's `auth` secret, with
  the miss and the mismatch returning the same message. Endpoints are validated
  https, length-capped, and passed through `ensure_public_host` in production.
  *One residual:* the SSRF check runs at subscribe/rotate, not at delivery, so a
  DNS rebind between the two is not caught. `webhook_service` re-checks at
  delivery; web push could adopt the same shape.
- **Injection.** No `eval`/`exec`/`pickle`/`yaml.load`/`subprocess`, no raw SQL,
  no string-built queries. Zero `ui.html`/`ui.markdown` calls in `pages/` or
  `theme/` — the `check_markdown_xss` hook enforces it, and the help/event-info
  renderer builds from typed blocks instead. The static spectator bracket
  renderer is the one place that emits markup by hand; every interpolation goes
  through `html.escape(quote=True)`, and the sole CSS-context value (the tenant
  brand primary) is validated to 6-digit hex before it gets there.
- **Session and headers.** `https_only` in production, `same_site=lax`,
  `STORAGE_SECRET` required and length-checked at startup. `X-Frame-Options:
  DENY`, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`, HSTS in
  production. `PublicCacheMiddleware` strips `Set-Cookie` from the two
  `Cache-Control: public` spectator routes, whose renders read no session.
- **Dependencies.** Current across the board — `starlette` 1.3.1, `fastapi`
  0.136.3, `cryptography` 48.0.1, `aiohttp` 3.14.1, `urllib3` 2.7.0. No known
  advisories. `pydantic` is pinned to `2.14.0a1`, an alpha; that is a stability
  and supply-chain question rather than a vulnerability, but a released version
  is the better resting place.
- **Secrets.** Nothing credential-shaped committed in the week's diff. Token
  auth failures log a prefix, never the value; audit rows record an endpoint
  host, never a push key.

## Defence-in-depth, no action needed

`sanitize_return_path` skips its ownership check entirely when `root_path` is
`''` (the bare platform host, or host mode), so a referrer of `//evil.com/x`
would pass through to `ui.navigate.to`. It is not reachable: the only writer is
`AuthMiddleware`, which builds the value from `request.url.path` and only after
`_matches_protected_route` matches — and no registered route pattern can match a
path whose first segment is empty. `safe_next`, the sibling used for the
cross-host handoff where the value *is* attacker-supplied, does reject `//`,
backslashes and control characters. Folding those same checks into
`sanitize_return_path` would cost nothing and remove the need to re-derive this
paragraph next time.
