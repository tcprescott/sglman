# Security audit — the week to 2026-08-03

Scope: every commit since `bc7ebeb` (2026-07-27), which is 328 commits and 835
files — the room-token kiosk view, the MCP write surface and its OAuth
authorization server, the cross-host login handoff, web push, reschedule
requests, payouts, equipment self-checkout, the static spectator brackets, and
the new REST routers behind all of them.

Method: read every entry surface that authenticates, authorizes, renders
attacker-controlled text, or makes an outbound request; trace each to the
service gate behind it, then follow anything that looked load-bearing out of
scope — which is how finding 0, the worst one here, turned up. Full suite green
(5426 passed), `ruff` clean, mypy ratchet at baseline.

## What was fixed here

### 0. Any community's STAFF could grant themselves SUPER_ADMIN — critical

Found while tracing the callers of the by-id user lookup (finding 3), which is
the only reason it turned up at all — it predates this week and nothing in the
week's diff caused it.

`Role.SUPER_ADMIN` is the one global role: its `UserRole` row carries
`tenant=NULL` and `AuthService.is_super_admin` bypasses every per-tenant gate.
`UserService.grant_role` gated on `can_grant_roles`, which is `is_staff` — and
`is_staff` is evaluated inside the *actor's own* community. So the check was
asking a tenant-local question about a platform-wide answer, and the enum's own
comment ("Not grantable per-tenant") was documentation with nothing enforcing it.

Two surfaces reached it, both one interaction deep:

- **The Users tab.** `theme/dialog/user_edit_dialog.py` built its role picker
  from `{r.value: … for r in Role}` — every member, Super Admin included. Any
  community's STAFF could open the dialog on themselves, tick it, save, and hold
  authority over every other community on the platform. `POST
  /api/users/{id}/roles` with `{"role": "super_admin"}` did the same over REST.
- **Discord role mappings.** `pages/admin_tabs/admin_discord_roles.py` offered
  the same unfiltered list as a mapping target, and `sync_user_roles` applies
  mappings on login. That one is a *standing* grant: map a guild role the
  community's own staff control, and it pays out on the holder's next sign-in.

Confirmed against the real database before fixing — a STAFF-only actor in a
throwaway tenant granted `SUPER_ADMIN` and `is_super_admin` returned True for
the target.

Fixed with one list, `Role.tenant_grantable()`, read by both pickers and both
service gates, so a future global role is excluded from all four at once instead
of in four places someone has to remember. `grant_role` and `revoke_role` refuse
the platform role outright rather than re-gating on super-admin: `/platform`'s
`TenantService.grant_super_admin` already does it properly, and one grant path
means one audit action — two paths writing the same row under different action
names is how a grant goes unnoticed. Revocation is gated too, or any community
could unseat the people who police it.

The mapping sync filters on the **stored row**, not just at create: a mapping
written before this guard existed, or restored from a backup, would otherwise
still pay out on the next login with nobody performing an action to notice.

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

### 3. The by-id user routes walked the whole platform — low/medium

`api/routers/users.py` gated on "self, or Staff", then loaded the user globally
(`load_user_or_404` → `UserService.get_user_by_id`, no tenant filter). The MCP
`get_user` tool did the same. So STAFF of any community could count `id=1..N`
and read every account on the platform: username, `discord_id`, display name,
pronouns, active flag. The sibling `list_users` was already narrowed for exactly
this — *"returning the platform's whole user table was a leak; there is
deliberately no `?scope=all`, which would re-open it behind a parameter"* — and
by-id reopened it behind a loop.

The caller trace turned up something sharper than the read. The same global
lookup fed `PATCH /users/{id}/admin`, whose `is_active` field is a *global*
account disable — so staff of any community could lock any account on the
platform out of every community, including ones they have nothing to do with.
`PATCH /users/{id}` (display name, pronouns) and the availability read had the
same shape.

Fixed with a second loader, `load_community_user_or_404`, scoped on
`TenantMembership` — the same basis the access gate and the person pickers use,
since holding a role in a tenant implies membership in it. It refuses with 404,
not 403, so "no such id" and "not in your community" read identically and the
status code is not a membership oracle. The actor always resolves themselves,
and a super-admin resolves anyone.

The **grant** routes deliberately keep the global loader: naming a tournament
admin or granting a role is *how someone joins* — `grant_role` calls
`ensure_member` as it goes — so scoping those would make the first grant
impossible. Both loaders now carry a docstring saying which is which, because
picking the wrong one is a cross-community leak.

Four API tests broke, all of them fixture artefacts rather than real behaviour:
they built the target with a bare `User.create`, which produces an account with
no membership — something no community's own pickers can see either. They now
use a `create_community_member` helper, which is what the app actually produces.
No production caller depends on the cross-community reach; the one flow that
deliberately reaches past members (the equipment borrower picker, for "someone
who just walked into the venue") goes through `get_community_people` with an
opt-in widening, not through these routes.

### 4. Web push did not re-check its destination at delivery — low

`ensure_public_host` ran when a subscription was stored but not when a push was
sent, so an endpoint whose host was repointed at an internal address afterwards
(slow DNS rebinding) would be dereferenced on a stale verdict. `webhook_service`
already re-checks at delivery; `_deliver_one` now does the same. It skips rather
than prunes — the host may resolve publicly again on the next send, and dropping
a real device's subscription over one transient answer is the worse failure.

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
  Delivery re-resolves the host too, since finding 4.
- **Discord DM interaction handlers** (`discordbot/`, six of them). The acting
  user comes from `interaction.user.id` — Discord-authenticated — never from the
  `custom_id`, which carries only an entity id. `_ack_common.run_dm_interaction`
  discovers the entity's tenant with a deliberately-unscoped read, then does
  every scoped call inside `tenant_scope`. Authorization is the service's, and
  each one holds: `acknowledge_crew_assignment` and `VolunteerScheduleService.
  acknowledge` both compare `user_id` before writing, `signup_crew` checks
  community membership, `record_opponent_agreement` refuses the requester and
  anyone who is not the other player, and `unwatch` is self-scoped by
  construction. Nothing found.
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
