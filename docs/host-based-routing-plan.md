# Host-based tenant routing — implementation plan

**Status:** proposal, not implemented. Design only.
**Depends on:** the shipped [multitenancy](features/multitenancy.md) layer.
**Supersedes:** the "deferred host-mode addressing" note in
[multitenancy-plan.md](multitenancy-plan.md) (Phase 3/4) — this doc is the
concrete follow-through for that one deferred piece.

This plan is written to be **analyzed adversarially before any code is written**.
It is deliberately explicit about the load-bearing assumptions, the one genuine
design fork (how OAuth survives per-host cookies), and the security surface it
opens. The last section lists the claims most worth attacking.

---

## 1. Goal and non-goals

**Goal.** Let a tenant be reached at its own custom domain
(`https://foo-community.gg/…`) instead of only at
`https://<PLATFORM_HOST>/t/<slug>/…`. A request whose `Host` matches a
`Tenant.domain` resolves to that tenant and serves the app's normal unprefixed
routes for it, with login and all tenant features working on that domain.

**In scope.**
- Host resolution in `TenantMiddleware`.
- Wiring the already-present-but-inert `PLATFORM_HOST` config.
- Making Discord login work on a custom domain (the hard part: per-host cookies).
- Keeping path mode (`/t/<slug>`) and the platform surface working unchanged.
- Tests, docs, and an operator rollout runbook.

**Non-goals (explicitly deferred).**
- Automatic domain-ownership verification (ACME/TXT challenge). A super-admin
  types the domain on `/platform`; we trust that, exactly as today.
- TLS certificate issuance/automation for custom domains — a reverse-proxy /
  ACME concern outside the app process.
- Making the *secondary* OAuth link flows (Challonge, Twitch, racetime, the
  Discord server-connect bot flow) host-native. Phase 1 keeps those on the
  platform host; see §4.5.
- A per-tenant "canonical domain" 301 redirect from `/t/<slug>` → domain
  (listed as optional in the original plan). Both entry points keep working.

---

## 2. Current state (what exists, what's inert)

| Piece | State today |
|---|---|
| `Tenant.domain` column | Exists (nullable, unique), set/validated on `/platform` (`TenantService._validate_domain`). **No request path reads it.** |
| `TenantService.get_by_domain()` / `TenantRepository.get_by_domain()` | Implemented, **zero callers** in the request path. |
| `get_platform_host()` (`application/utils/environment.py`) | Implemented, **zero callers** — so the documented `PLATFORM_HOST` env var is currently inert (flagged in `docs/reviews/2026-07-code-quality-audit.md`). |
| `TenantMiddleware` (`middleware/tenant.py`) | Resolves **only** `^/t/<slug>` by path; never reads `Host`. No `/t/` prefix ⇒ platform surface (no tenant). |
| Session cookie (`frontend.py:134`) | NiceGUI SessionMiddleware, `same_site='lax'`, `https_only` in prod, **no `domain=`** ⇒ host-only cookie. |
| OAuth (`pages/auth.py`) | Single redirect URI derived from `BASE_URL` (or `REDIRECT_URL`), built at request time; tenant return path carried in the session, not the URL. |

So the "storage + lookup" half of host mode is built; the "resolution +
auth" half is missing. This plan builds the missing half.

---

## 3. Resolution design (`middleware/tenant.py`)

### 3.1 Resolution order

`TenantMiddleware.dispatch` gains a host branch. Proposed order (host lowercased,
compared to `get_platform_host()`):

1. **Excluded transport/API paths** (`/_nicegui`, `/static`, `/api`, `/sw.js`) →
   passthrough, no tenant (unchanged). The REST API keeps deriving its tenant
   from the bearer token.
2. **Path mode** — path matches `^/t/<slug>` → resolve slug, rewrite scope
   (`root_path = /t/<slug>`), set tenant (unchanged). Works on **any** host.
3. **Host mode** — `host` is non-empty, `host != PLATFORM_HOST`, and
   `get_by_domain(host)` returns an **active** tenant → set tenant context and
   **leave `scope['path']`/`root_path` untouched** (the whole host is the
   tenant; unprefixed routes already match, absolute links stay on-host). An
   **inactive** matched domain → 404 (parity with inactive slug).
4. **Platform surface** — anything else (host is `PLATFORM_HOST`, or an unknown
   host) → no tenant context (unchanged: landing page, `/platform`, OAuth
   callbacks).

**Why path mode before host mode?** So every tenant stays reachable at
`/t/<slug>` on the platform host even after it gets a domain, and so a
misconfigured `Host` header can never *hide* the explicit path form. On a custom
domain a stray `/t/<other>` path would resolve `<other>` in path mode — harmless
(it only ever serves that tenant's *own* isolated data, never a cross-tenant
leak), if slightly odd. The alternative (host wins, `/t/*` becomes a dead route
on a custom domain) is also defensible; **this is an open question for review
(§10).**

**Unknown host is lenient, not 404.** A `Host` that is neither `PLATFORM_HOST`
nor a known domain (health checks by IP, an unconfigured CNAME, a scanner) falls
through to the platform surface, exactly as today. This keeps the change
strictly additive: host mode only *adds* resolution for configured domains and
cannot regress any existing request. (The original plan said "unknown host →
404"; we deliberately soften that to avoid breaking IP/health-check traffic —
**flagged for review, §10.**)

### 3.2 `root_path` stays empty in host mode

Path mode needs `root_path=/t/<slug>` so links/redirects re-acquire the prefix.
Host mode needs the opposite: `root_path=''`, because the tenant owns the whole
host and every absolute link (`ui.navigate.to('/admin')`, server-side
`RedirectResponse('/login')`) must stay a bare path on the same host. This is
already the value produced for the platform surface, so most link-building code
needs no change. `TransportPrefixMiddleware` is a **no-op** in host mode (there
is no `/t/<slug>` prefix on asset/websocket URLs to strip), so NiceGUI assets and
the socket.io connection are served at their bare paths and pass straight
through. The per-client tenant stash (written at page build in
`@protected_page`/`home`) still feeds websocket UI handlers, identically to path
mode.

### 3.3 Reading the host correctly (proxy reality)

In production the app sits behind a TLS-terminating reverse proxy. The `Host`
header seen by the app depends on proxy config:
- If the proxy forwards the original `Host` (common for nginx `proxy_set_header
  Host $host`), `request.headers['host']` is the browser's host — use it.
- If the proxy rewrites `Host`, the original is in `X-Forwarded-Host`.

**Decision:** resolve the effective host as
`(X-Forwarded-Host split on comma, first value) or Host`, lowercased, matched
exactly against `PLATFORM_HOST` and `Tenant.domain`. But trusting
`X-Forwarded-Host` blindly is a spoofing vector (§8). Gate it behind a
`TRUST_FORWARDED_HOST` env flag (default **off**); when off, use only the real
`Host` header. Document that operators terminating TLS at a proxy must either
forward `Host` verbatim or set `TRUST_FORWARDED_HOST=1` with a trusted proxy in
front. Ports: browsers omit `:443`/`:80`, so stored domains are bare
(`foo.gg`); we match the full host string and document that `Tenant.domain`
must not include a port. (`get_platform_host()` already returns netloc *with*
port for local dev; keep that asymmetry documented.)

### 3.4 Caching

`TenantService.get_by_slug` is cached with a FIFO cap; `get_by_domain` is **not**
cached yet. Add a parallel `_cache_by_domain` (same cap, same wholesale
invalidation on any tenant write via `_clear_cache()`), because host mode puts
`get_by_domain` on the hot path of every custom-domain request. Negative results
must be cached too (an attacker hitting the platform IP with random `Host`
values would otherwise query the DB each time) — but that means the FIFO cap and
`_clear_cache()` on write are load-bearing; call it out for review.

### 3.5 Dev / test story

- **Unit-testable without DNS:** drive the middleware with an explicit `Host`
  header (`base_url='http://foo.gg'`) exactly like `test_tenant_middleware.py`
  already drives path mode. No hosts-file needed for tests.
- **Local manual testing:** `foo.localhost` resolves to `127.0.0.1` in modern
  browsers/Chromium, so a tenant with `domain='foo.localhost:8000'` is reachable
  at `http://foo.localhost:8000/` with no `/etc/hosts` edit. `MOCK_DISCORD`
  login already works per-host, so the full logged-in flow is exercisable
  locally and by the `/ui-validation` browser loop.
- Seed a domain'd tenant in `scripts/seed_dev.py` so the feature is visible in
  dev (the repo's rule: "a feature the seed never creates is a feature no one
  can see").

---

## 4. The hard part: auth & sessions under per-host cookies

### 4.1 The core constraint

The session cookie is **host-only** (no `Domain` attribute). Therefore a login
on `PLATFORM_HOST` is **not** visible on `foo.gg`, and vice-versa. There is no
way to share one cookie across unrelated apex domains — this is a browser
invariant, not a config we can flip. Consequence: **a user must authenticate on
each host they use.** That is acceptable (arguably desirable isolation), but it
means the OAuth flow must *complete on the custom domain* so the resulting
session cookie lands on that domain. This is the whole difficulty; everything
below is about satisfying it.

### 4.2 The fork: two ways to land an authenticated session on `foo.gg`

**Design A — host-local OAuth (recommended for Phase 1).**
`foo.gg/login` runs the *entire* Discord flow on `foo.gg`: it sends
`redirect_uri=https://foo.gg/oauth/callback`, Discord bounces back to
`foo.gg/oauth/callback` (same host ⇒ same cookie ⇒ `oauth_state` matches), and
the callback sets `authenticated` in `foo.gg`'s session. Only code change:
`_redirect_uri()` becomes host-aware.

- **Pros:** tiny, reuses the existing, tested flow; no new cryptographic
  artifact; no cross-host redirect to secure.
- **Cons:** every custom domain's `https://<domain>/oauth/callback` must be
  registered as a redirect URI in the Discord Developer Portal. Discord caps
  redirect URIs (~10), so this does **not** scale to many domains and adding a
  domain is a manual provider-side step (not self-serve).

**Design B — central callback + signed-token handoff (the original plan's
sketch; recommended only if domain count grows).**
OAuth always happens on `PLATFORM_HOST` (single registered redirect URI,
unchanged). `foo.gg/login` → redirect to `PLATFORM_HOST/oauth/start?next=<foo.gg
return url>` → normal Discord flow on the platform host → callback mints a
**short-lived, single-use, host-bound, signed** handoff token and redirects the
browser to `https://foo.gg/session/claim?token=…` → `foo.gg` validates the token
(shared `STORAGE_SECRET`) and writes its own host-local session.

- **Pros:** one registered redirect URI per provider forever; adding a domain
  needs zero provider config; scales to arbitrarily many domains.
- **Cons:** a real bearer credential now travels in a URL (browser history,
  `Referer`, proxy logs). Requires careful token design: single-use nonce, tight
  TTL (≤30 s), bound to the exact target host **and** the resolved `discord_id`,
  plus strict allow-listing of `next`/target host against known `Tenant.domain`
  values to prevent open-redirect / token-exfiltration. More surface, more tests.

**Recommendation:** ship **Design A** first (host-local Discord login only),
because SGL realistically has a handful of communities and at most a few custom
domains, so the Discord-registration ceiling is not yet binding, and A adds no
new security-sensitive machinery. Document B as the migration path if/when the
domain count approaches the provider limit. **This recommendation is the single
most important thing to attack in review (§10).**

### 4.3 Making `_redirect_uri()` host-aware (Design A)

Today (`pages/auth.py:52`): `REDIRECT_URL` or `f"{get_base_url()}/oauth/callback"`
— always the platform host. Proposed:

- `/login` (has `request`): build the redirect from the **effective request
  host** *only when that host resolves to a known active tenant domain or is the
  platform host*; otherwise fall back to the platform host. **Never reflect an
  unknown/attacker-supplied `Host` into a `redirect_uri`** (§8 — this is the
  sharpest security edge of Design A). Honor the `REDIRECT_URL`/`OAUTH_URL`
  single-value overrides only for the platform host.
- `/oauth/callback` (token-exchange leg): the callback already reads
  `window.location.href`; derive the same `redirect_uri` from that URL's scheme
  + host so the value passed to `get_access_token(code, redirect_uri)` matches
  the one used at `/login` (Discord requires an exact match). Because Discord
  only ever redirects to a **registered** URI, the callback host is inherently
  trustworthy here.
- Scheme behind a proxy: prefer `X-Forwarded-Proto` (when `TRUST_FORWARDED_HOST`
  is on), else `request.url.scheme`. The callback leg gets the real scheme from
  `window.location` for free.

### 4.4 Logout, referrer, redirects

- `/logout` already builds `RedirectResponse(tenant_home(root_path))`; with
  `root_path=''` in host mode that is `/`, which stays on `foo.gg`. No change.
- `AuthMiddleware` writes `referrer_path = f'{root_path}{path}'` and redirects to
  `f'{root_path}/login'`. In host mode `root_path=''`, so these become bare
  `/admin` and `/login` — correct for a custom domain. `sanitize_return_path`
  with `root_path=''` already handles the bare case (rejects auth routes,
  returns home otherwise). No change, but **add explicit host-mode tests** since
  this path was only ever exercised with a non-empty `root_path` (path mode) or
  the platform surface.
- MOCK_DISCORD login is already host-local (it sets the cookie on whatever host
  served the picker and navigates to `referrer_path`), so dev/UI-validation
  works with zero auth changes.

### 4.5 The other OAuth providers (Phase 1 stance)

Challonge, Twitch, and racetime linking, plus the Discord **server-connect** bot
flow, are all secondary flows initiated from *inside* an already-authenticated
session and are admin/opt-in. Phase 1 leaves their callbacks on the platform
host. Practical consequence: to link Challonge/Twitch/racetime, a user does it
from the path-mode (`/t/<slug>`) surface, not the custom domain — or we make
each host-aware later (Design A repeated per provider, or Design B generalized).
Document this limitation prominently; do **not** silently half-wire it. **Open
question (§10):** is a custom-domain tenant that cannot link Challonge on its own
domain acceptable for v1?

---

## 5. Platform surface & landing — verify unchanged

- `/platform` gates on `get_current_tenant_id() is None` **and** super-admin. On
  a custom domain the tenant context is set, so `/platform` there correctly
  404s. `/platform` remains reachable only on `PLATFORM_HOST`. No change.
- The community-picker landing (`_render_platform_landing`) renders only when
  `tid is None` — i.e. only on `PLATFORM_HOST`. Its per-tenant links are
  `/t/<slug>/` (path mode), which keep working. Optionally, later, link a
  domain'd tenant to its domain instead — deferred.
- `@protected_page`'s "no tenant ⇒ 404" guard is unaffected: host mode *sets* a
  tenant, so protected pages authorize normally on the custom domain.

---

## 6. Other URL builders to audit (not all in scope to fix)

Absolute URLs built from `BASE_URL` point at the platform host with **no**
tenant context, so they only resolve correctly in path mode when they already
include `/t/<slug>` — and today they do **not**:
- **Equipment QR codes** (`{BASE_URL}/equipment/{id}`) and any `BASE_URL`-derived
  deep link resolve to the platform surface (no tenant) and 404 under
  multitenancy *already*, independent of host mode. Host mode does not worsen
  this, but the audit should record it (candidate follow-up: build tenant deep
  links from a `tenant_base_url()` helper that knows the tenant's domain or
  `/t/<slug>`).
- **Web-push deep links** and **Discord DM links** have the same property.

Host mode makes a *correct* per-tenant absolute-URL helper more valuable, but
fixing those links is **out of scope** here; the plan only flags them so the
review can decide whether to fold one in.

---

## 7. Config / env

| Var | New? | Purpose |
|---|---|---|
| `PLATFORM_HOST` | exists, wire it up | The bare host that is the platform surface + path-mode host. Now actually read by `TenantMiddleware`. Defaults to `BASE_URL`'s netloc. |
| `TRUST_FORWARDED_HOST` | new, default off | Honor `X-Forwarded-Host`/`-Proto` for host + scheme resolution. On only behind a trusted proxy. |

No new column: `Tenant.domain` already exists. Update `.env.example`,
`docs/deployment.md` env table, and `docs/reference/authentication.md`.

---

## 8. Security considerations

1. **Host-header injection into `redirect_uri` (Design A's sharpest edge).** If
   `/login` reflected an arbitrary `Host` into `redirect_uri`, an attacker could
   try to route the OAuth `code` to their host. Two independent mitigations:
   (a) only build the redirect from a host that resolves to a **known active
   tenant domain** (or the platform host), never an arbitrary one; (b) Discord
   itself only redirects to **registered** URIs. Both must hold; the test suite
   asserts (a).
2. **Tenant selection via forged `Host`.** Forging `Host: foo.gg` serves foo's
   tenant — but only foo's own isolated data, foo's own login. It is **not** a
   cross-tenant read (tenant isolation is enforced by `tenant_id` on every
   query, with the leak tests behind it). The risk is limited to "which
   community's public shell do I see", not data disclosure.
3. **`X-Forwarded-Host` spoofing.** Trusting it unconditionally lets any client
   pick the tenant. Hence `TRUST_FORWARDED_HOST` defaults off and is only for a
   trusted-proxy topology.
4. **Cache poisoning.** Any shared HTTP cache in front of the app must key on
   `Host` (or `Vary: Host` semantics) now that the same path yields different
   tenants per host. Document it; the app sets no such cache itself.
5. **Design B token risks** (if/when chosen): replay, TTL, host binding,
   `discord_id` binding, single-use nonce, `next` open-redirect allow-listing.
   Enumerated in §4.2; each needs a test.
6. **Domain ownership.** No verification today: a super-admin can enter any
   domain, including one they don't own (it simply won't route until that
   domain's DNS points here, and TLS is provisioned). Trusted-admin assumption;
   note ACME/TXT verification as a future hardening.
7. **Cookie flags unchanged.** `same_site='lax'`, `https_only` in prod stay
   correct per-host. `lax` is compatible with the top-level GET redirect Discord
   performs back to the callback.

---

## 9. Testing plan

Extend `tests/test_tenant_middleware.py` and add auth tests:

- **Resolution:** `Host=foo.gg` (active domain) → tenant set, `path` and
  `root_path` untouched (`root_path==''`). Inactive domain → 404. Unknown host →
  platform surface (no tenant). `Host=PLATFORM_HOST` → platform surface. Path
  mode still wins on any host (`foo.gg/t/beta/…` → beta).
- **Precedence & isolation:** a leak-style test that a request on `foo.gg` only
  ever sees foo's rows (reuse the isolation-test scaffold).
- **Forwarded host:** `X-Forwarded-Host` honored only when
  `TRUST_FORWARDED_HOST=1`; ignored otherwise.
- **redirect_uri host-awareness:** `/login` on a known domain builds
  `https://foo.gg/oauth/callback`; on the platform host builds the platform URI;
  an **unknown** `Host` does **not** get reflected (falls back to platform).
- **Referrer/redirect in host mode:** `AuthMiddleware` on `foo.gg/admin`
  (unauthenticated) sets `referrer_path='/admin'` and redirects to `/login`
  (bare). `sanitize_return_path('', …)` cases.
- **Caching:** `get_by_domain` cache hit/miss + invalidation on tenant update;
  negative-lookup cap.
- **Design B (only if chosen):** token TTL expiry, single-use, host/`discord_id`
  binding, `next` allow-listing.
- Full existing suite must stay green (the change is additive; assert no
  path-mode regressions).

---

## 10. Open questions — attack these in the adversarial review

1. **A vs B.** Is host-local OAuth (A) the right Phase-1 call, or does the
   Discord redirect-URI ceiling / the per-provider multiplication make the
   signed-handoff (B) worth its extra surface *now*? What is the real domain
   count we're designing for?
2. **Precedence.** Should host mode win over an explicit `/t/<slug>` path on a
   custom domain (host authoritative), or should path mode keep priority
   (current proposal)? Which is less surprising / safer?
3. **Unknown host.** Lenient (fall through to platform surface, proposed) vs
   strict 404 (original plan). Does lenient enable any abuse, or is it just
   correct handling of health checks / scanners?
4. **Secondary providers.** Is a v1 where Challonge/Twitch/racetime linking only
   works on the path-mode host acceptable, or is that too sharp an edge?
5. **Forwarded-host default.** Is default-off the right safe default, or will it
   silently break the first real proxy deployment (and should the runbook lead
   with it)?
6. **Cross-host absolute links (§6).** Should this plan fold in a
   `tenant_base_url()` deep-link fix, or is leaving QR/DM links platform-host is
   acceptable for now?
7. **`domain` uniqueness & normalization.** Is exact-string match enough, or do
   we need apex/`www` canonicalization, IDNA/punycode handling, trailing-dot
   normalization?

---

## 11. Phased implementation checklist (once the design is settled)

**Phase 1 — resolution + Discord host-local login (Design A):**
1. Wire `get_platform_host()` + add effective-host resolution (with optional
   forwarded-host) to `TenantMiddleware`; host-mode branch; `_cache_by_domain`.
2. Make `_redirect_uri()` host-aware with the known-domain guard.
3. Add host-mode + redirect_uri + referrer tests; keep path-mode green.
4. `.env.example` + deployment/auth docs; note the Discord redirect-URI
   registration step per domain and the DNS/TLS prerequisites.
5. Seed a domain'd tenant in `scripts/seed_dev.py`; verify via `/ui-validation`.
6. Update `features/multitenancy.md` (host mode now live) and this doc's status.

**Phase 2 (only if needed) — scale-out:** Design B signed-handoff, or
host-native secondary providers, plus `tenant_base_url()` deep links and a
per-tenant canonical-domain 301.
