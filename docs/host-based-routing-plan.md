# Host-based tenant routing — implementation plan

**Status:** **Phase 1 implemented** (Design A — host-local Discord login) and
**Phase 2 partially implemented.** Shipped in Phase 2: the Design B signed-handoff
for Discord login (flag-gated `HOST_OAUTH_MODE=handoff`, default `local`) and the
`tenant_base_url()` / `tenant_url()` deep-link helper (wired into the equipment
QR link). **Still deferred from Phase 2:** host-native *secondary* providers over
the handoff (the Phase-1 platform-host detour still handles them), and the forced
`/t/<slug>`→domain 301 (skipped: it forces a re-auth across the host boundary; the
deep-link helper delivers the canonical-domain benefit for generated links without
that cost). The sections below are retained as the design record.
**Depends on:** the shipped [multitenancy](features/multitenancy.md) layer.
**Supersedes:** the "deferred host-mode addressing" note in
[multitenancy-plan.md](multitenancy-plan.md) (Phase 3/4) — this doc is the
concrete follow-through for that one deferred piece.
**Review:** a round-1 adversarial review has run; its outcome is **§12**, which
**supersedes** earlier sections where they conflict. The three must-fix items
are folded in below (§3.3, §4.2–§4.5, §6, §7) and §10 is now resolved. Read §12
before implementing.

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
routes for it, with **Discord login and the core tenant surface** working on
that domain. (Secondary OAuth *link* flows — Challonge / Twitch / racetime and
the Discord server-connect flow — stay on the platform host in Phase 1 and are
**hidden** on custom-domain hosts; see §4.5 and §12 must-fix 2. The earlier
"all tenant features" wording overclaimed.)

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
   passthrough, no tenant (unchanged), on **every** host. The REST API keeps
   deriving its tenant from the bearer token — "one domain == one tenant" does
   **not** extend to `/api`, which stays host-agnostic.
2. **Host mode (authoritative for a custom domain)** — `host` is non-empty,
   `host != PLATFORM_HOST`, and `get_by_domain(host)` returns an **active**
   tenant → set tenant context and **leave `scope['path']`/`root_path`
   untouched** (the whole host is the tenant; unprefixed routes already match,
   absolute links stay on-host). A matched-but-**inactive** domain is **not**
   host mode: it falls through leniently to path/platform exactly like an unknown
   host (below), so `/t/<slug>` stays reachable on that host and deactivating one
   tenant never 404s the others. (Revised from the original "inactive → 404" after
   round-2 review flagged the asymmetry with unknown-host leniency.)
3. **Path mode (on `PLATFORM_HOST`)** — path matches `^/t/<slug>` → resolve slug,
   rewrite scope (`root_path=/t/<slug>`), set tenant (unchanged).
4. **Platform surface** — `PLATFORM_HOST` with no `/t/` prefix, **or an unknown
   host** → no tenant context (landing page, `/platform`, OAuth callbacks).

**Host is authoritative on a custom domain (resolved, §10.2).** Because host mode
(step 2) runs before path mode (step 3), a stray `/t/<other>` on `foo.gg` is left
as the literal path `/t/<other>` — which is not a registered route, so it
**404s** (optionally 301 to the canonical host). One domain therefore serves
**exactly one** tenant, removing the "why is another community's shell rendering
on my domain" surprise. Path mode stays authoritative only on `PLATFORM_HOST`,
where every tenant remains reachable at `/t/<slug>` regardless of any domain.

**Unknown host is lenient — but not silent (resolved, §10.3).** A `Host` that is
neither `PLATFORM_HOST` nor a known domain (health checks by IP, an unconfigured
CNAME, a scanner) falls through to the platform surface, exactly as today — this
keeps the change strictly additive and avoids 404ing health traffic. **But** to
catch the most likely rollout failure (a proxy that doesn't forward `Host`
verbatim, so a *configured* domain silently renders the platform surface), emit a
**rate-limited WARNING** whenever a non-empty, non-`PLATFORM_HOST`, non-path-mode
request misses `get_by_domain`, and **log the resolved `PLATFORM_HOST` at
startup**. Leniency also keeps the existing test suite green (see §9).

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
`(X-Forwarded-Host, last value) or Host`, run through the **same normalization
used at write-time** (§7), matched exactly against the normalized
`PLATFORM_HOST` and `Tenant.domain`. Two corrections from review:

- **Take the _last_ `X-Forwarded-Host` value, not the first.** `X-Forwarded-*`
  is append-ordered (leftmost = original client-supplied, rightmost = set by the
  nearest/trusted proxy), so the first element is attacker-controllable when a
  proxy *appends* rather than replaces. Use the last comma-separated value. Still
  gate the whole `X-Forwarded-Host`/`-Proto` path behind `TRUST_FORWARDED_HOST`
  (default **off**); when off, use only the real `Host`. Operators terminating
  TLS at a proxy must either forward `Host` verbatim or set
  `TRUST_FORWARDED_HOST=1` behind a trusted proxy.
- **The invariant is "`Tenant.domain` == the normalized effective `Host`,
  verbatim,"** not "must not include a port." Browsers omit `:443`/`:80`, so a
  production domain is bare (`foo.gg`); local dev uses `foo.localhost:8000`
  **with** its non-default port (§3.5). Normalization (§7) is what makes both
  ends agree — it strips default ports but preserves non-default ones.
  (`get_platform_host()` returns netloc *with* port for local dev; the same
  normalization applies to it.)

### 3.4 Caching

`TenantService.get_by_slug` is cached with a FIFO cap; `get_by_domain` is **not**
cached yet. Add a parallel `_cache_by_domain`, wired into `_clear_cache()` (which
today clears only the slug/guild dicts — it must clear the new one too), because
host mode puts `get_by_domain` on the hot path of every custom-domain request.
**Cap negatives separately from positives** (or skip caching syntactically
implausible hosts): a flood of *distinct* random `Host` values in one shared
FIFO pool would evict the handful of real domains — and negative caching does
nothing against distinct hosts anyway (it only helps repeated ones). The
platform-host short-circuit (§3.1 step 3 skips `get_by_domain` when
`host == PLATFORM_HOST`) already spares the common case.

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
the callback sets `authenticated` in `foo.gg`'s session. The code change is **not**
"only `_redirect_uri()` becomes host-aware" (an understatement the review
flagged): it touches `_redirect_uri`'s signature, `_oauth_url`'s host threading,
`/login`, **and** the callback's exchange leg — see §4.3, which the review
rewrote into a single canonical builder to avoid a real default-config outage.

- **Pros:** small, reuses the existing, tested flow; no new cryptographic
  artifact; no cross-host redirect to secure.
- **Cons:** every custom domain's `https://<domain>/oauth/callback` must be
  registered as a redirect URI in the Discord Developer Portal. The single OAuth
  app **already spends 2 of its ~10 slots** (`{BASE_URL}/oauth/callback` +
  `{BASE_URL}/oauth/discord/connect/callback`), leaving **~8** for custom
  domains — and a future host-native connect flow would cost 2 per domain. So
  set an explicit numeric trigger to migrate to Design B: **`registered_domains +
  reserved_slots > 8`**. Adding a domain is a manual provider-side step (not
  self-serve).

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

Today (`pages/auth.py:52-61`): `REDIRECT_URL` or
`f"{get_base_url()}/oauth/callback"` — always the platform host, scheme baked in
from `BASE_URL` (always `https`), and — critically — **the same builder is
called by both legs** (`/login` via `_oauth_url`, and the callback's token
exchange at `pages/auth.py:214-216`), so the authorize string and the exchange
string are byte-identical *by construction*. Discord requires them to match
exactly. **The naïve "derive `/login` from `request.url.scheme` + `Host`, derive
the callback from `window.location`" approach breaks this and must not be used**
(review must-fix 1), for two reasons:

1. **Default-config outage.** `start.sh` runs uvicorn with no
   `--forwarded-allow-ips`, so behind an off-box TLS-terminating proxy
   `request.url.scheme == 'http'`. With `TRUST_FORWARDED_HOST` default-off, a
   `request`-derived `/login` would build `http://…/oauth/callback`, which
   Discord rejects against the registered `https://` URI — breaking login **even
   on the platform host**, before any custom domain exists.
2. **Two-leg desync.** The callback (`oauth_callback(client)`, `pages/auth.py:182`)
   has no `request`; any independent derivation risks a mismatch that fails the
   exchange.

**Corrected design — one canonical builder, host from the _resolved tenant_, not
the request.** Add a single helper that both legs call:

- For a **custom-domain** request the tenant is already resolved (host mode set
  the context), so build `https://{tenant.domain}/oauth/callback` from the
  **stored `Tenant.domain`** (`get_by_id(current_tenant_id()).domain`) — never
  from the reflected `Host`. This closes the host-injection edge (§8.1) *by
  construction* rather than by a reflect-then-validate guard.
- For the **platform host**, keep `REDIRECT_URL`/`{BASE_URL}/oauth/callback`
  (unchanged).
- **Force `https://`** for any non-localhost host; permit `http`/`:8000` only for
  the `*.localhost` dev case (§3.5). Do **not** read scheme from
  `request.url.scheme`.
- The callback leg recovers the tenant the same way (it runs on the custom
  domain, or resolves via the same helper) and therefore reproduces the identical
  string. A §9 test asserts the two legs match behind a scheme-rewriting proxy.

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
session and are admin/opt-in. Their callbacks stay on the platform host in
Phase 1. **But leaving them "deferred" is not enough** (review must-fix 2): each
one writes its CSRF state + return path into the **host-only** session cookie and
redirects to a **single registered platform-host callback**. On `foo.gg`, the
"Connect Challonge" / "Link Twitch" / etc. buttons are plain navigations to bare
paths, so clicking one initiates on `foo.gg`, the provider bounces to the
platform-host callback where **no `foo.gg` cookie exists** → state/return absent,
`get_user_from_discord_id(None)` is `None` → the user is silently dumped on the
community picker with **no link created and no error**. That is exactly the
"silently half-wire it" failure to avoid.

**Phase-1 requirement:** on a custom-domain host, **hide the secondary-link
buttons and gate their initiation routes** (`/challonge/connect`,
`/challonge/link`, `/<provider>/link`, `/oauth/discord/connect/*`) — block them
(or redirect the *initiation* to the platform surface), and add a §9 test
asserting they are blocked, not silently failing. Linking is done from the
path-mode (`/t/<slug>`) surface in v1.

Note for later: "Design A repeated per provider" is **not** a valid path for
**single-URI** providers — Challonge validates against one registered
`redirect_uri`, so it can *never* be made host-native without a Design-B-style
handoff. Only Design B generalizes to them.

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

Correction from review: the draft's blanket claim that `BASE_URL`-derived deep
links "404 under multitenancy already" was **wrong** for the example it cited.

- **Equipment QR codes already work.** `pages/equipment.py` builds
  `{BASE_URL}/t/<slug>/equipment/<id>` — tenant-qualified **path mode**, not
  `{BASE_URL}/equipment/{id}`. So host mode's motivation here is not "fix a
  break" but "optionally point a tenant's deep links at *its own domain* instead
  of the `/t/<slug>` path form."
- **Other builders must be checked individually, not assumed identical.**
  Web-push deep links default to `{BASE_URL}/` (platform root,
  `web_push_service.py`); Discord DM links vary. Whether each is already
  tenant-qualified is a per-call-site audit, not a blanket property.

A per-tenant absolute-URL helper (`tenant_base_url()`, aware of a tenant's
domain-or-`/t/<slug>`) is a clean **Phase 2** item. Fixing these links is
**out of scope** here.

---

## 7. Config / env

| Var | New? | Purpose |
|---|---|---|
| `PLATFORM_HOST` | exists, wire it up | The bare host that is the platform surface + path-mode host. Now actually read by `TenantMiddleware`. Defaults to `BASE_URL`'s netloc. **Log the resolved value at startup** so a proxy mismatch is visible. |
| `TRUST_FORWARDED_HOST` | new, default off | Honor `X-Forwarded-Host`/`-Proto` for host + scheme resolution. On only behind a trusted proxy. |

No new column: `Tenant.domain` already exists. Update `.env.example`,
`docs/deployment.md` env table, and `docs/reference/authentication.md`.

**`Tenant.domain` normalization contract (review must-fix 3 — do before Phase 1).**
Today `_validate_domain` (`tenant_service.py:126-130`) only does `strip().lower()`
+ a uniqueness check, and `pages/platform.py`'s domain field is a bare `ui.input`.
So a super-admin typing `https://foo.gg`, `foo.gg:443`, `foo.gg/`, `foo.gg.`, or
a stray space **stores successfully and then silently never routes** (falls
through to the platform surface, no error). Fix: `_validate_domain` applies **one
normalization, used identically at write-time and at resolution (§3.3)** —
lowercase; strip scheme/path/whitespace; strip trailing dot; strip default
`:80`/`:443` while **preserving** a non-default port (`:8000` for dev); IDNA /
punycode; validate against a hostname regex; and **reject a value equal to the
normalized `PLATFORM_HOST`** — raising `ValueError` so `/platform` surfaces it
immediately instead of failing silently at request time.

**Trusted-proxy flag naming.** The repo already ships `TRUST_PROXY_FORWARDED_FOR`
(gates `X-Forwarded-For` trust for the rate limiter, `api/rate_limit.py:70`). The
new `TRUST_FORWARDED_HOST` encodes the same "trusted proxy in front" precondition
for a different header. They are **not** interchangeable (one governs client-IP,
the other host/scheme), so keep them separate but **cross-reference both in the
env table** and note in the runbook that a proxy deployment almost certainly
wants both. Add `TRUST_FORWARDED_HOST` to `.env.example`.

---

## 8. Security considerations

1. **Host-header injection into `redirect_uri` (Design A's sharpest edge).**
   Closed **by construction** in the corrected §4.3: the `redirect_uri` is built
   from the **resolved tenant's stored `Tenant.domain`**, never from the reflected
   `Host` header — so there is nothing attacker-controlled to reflect. (Belt and
   braces: Discord only redirects to **registered** URIs anyway.) This is
   stronger than the draft's original reflect-then-validate guard.
2. **Tenant selection via forged `Host`.** Forging `Host: foo.gg` serves foo's
   tenant — but only foo's own isolated data, foo's own login. It is **not** a
   cross-tenant read (tenant isolation is enforced by `tenant_id` on every
   query, with the leak tests behind it). The risk is limited to "which
   community's public shell do I see", not data disclosure.
3. **`X-Forwarded-Host` spoofing.** Trusting it unconditionally lets any client
   pick the tenant. Hence `TRUST_FORWARDED_HOST` defaults off and is only for a
   trusted-proxy topology — **and take the _last_ value, not the first** (§3.3),
   since the header is append-ordered and the leftmost element is
   client-controllable. Worst case is still only tenant-*shell* selection, not a
   data leak (item 2), but fix the parsing rule regardless.
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
- **Precedence & isolation:** host-authoritative — `foo.gg/t/beta/admin` 404s (or
  301s) on a custom domain; path mode resolves only on `PLATFORM_HOST`. Plus a
  leak-style test that a request on `foo.gg` only ever sees foo's rows (reuse the
  isolation-test scaffold).
- **Forwarded host:** `X-Forwarded-Host` honored only when
  `TRUST_FORWARDED_HOST=1`; ignored otherwise; and with a **two-element** header
  the **last** value wins (assert the leftmost/forged element is not used).
- **`domain` normalization:** `_validate_domain` rejects `https://…`, a path, a
  trailing dot, `== PLATFORM_HOST`; strips default ports but keeps `:8000`;
  round-trips so a normalized `domain` matches the normalized effective `Host`.
- **redirect_uri (the make-or-break test):** built from the **resolved tenant's
  stored `domain`** (not the `Host`), and the `/login` authorize leg and the
  callback exchange leg produce a **byte-identical** string **behind a
  scheme-rewriting proxy** (`request.url.scheme == 'http'`, `TRUST_FORWARDED_HOST`
  off) — i.e. both are `https://…`. Platform host still uses the platform URI.
- **Secondary providers blocked on custom domains:** initiating
  `/challonge/connect` / `/<provider>/link` / `/oauth/discord/connect/*` on
  `foo.gg` is **blocked (or redirected to the platform surface), not silently
  failing**, and the buttons are hidden there.
- **Referrer/redirect in host mode:** `AuthMiddleware` on `foo.gg/admin`
  (unauthenticated) sets `referrer_path='/admin'` and redirects to `/login`
  (bare). `sanitize_return_path('', …)` cases.
- **Caching:** `get_by_domain` cache hit/miss + invalidation on tenant update;
  negatives capped separately so a distinct-`Host` flood can't evict positives.
- **Design B (only if chosen):** token TTL expiry, single-use nonce, host/
  `discord_id` binding, `next` allow-listing.
- **Suite stays green — but set `PLATFORM_HOST` in the harness.** The existing
  `test_tenant_middleware.py` drives `Host: platform`, which is an *unknown* host
  under the default `PLATFORM_HOST=localhost:8000`; that only passes because the
  chosen unknown-host behavior is *lenient* (§10.3). To keep the suite green
  under either leniency choice, set `PLATFORM_HOST='platform'` in the harness and
  seed a `Tenant.domain` for the host-mode cases. Assert no path-mode
  regressions.

---

## 10. Resolved decisions (post round-1 review)

Each of the original open questions now has a decision from the adversarial
review (§12); the sections above are updated to match.

1. **A vs B →** ship **A** (host-local OAuth) for Phase 1 — SGL's domain count is
   small and B's URL-borne bearer token is real added surface. **But** fix the
   `redirect_uri` builder first (§4.3 / §12 must-fix 1); the real Discord slot
   budget is **~8** (2 already used), so migrate to B when
   `domains + reserved_slots > 8`.
2. **Precedence → host-authoritative** on a custom domain: `/t/<other>` 404s
   there; path mode stays authoritative only on `PLATFORM_HOST` (§3.1).
3. **Unknown host → lenient**, plus a rate-limited WARNING on a *configured*-domain
   miss and a startup log of `PLATFORM_HOST` (§3.1). Also keeps the suite green.
4. **Secondary providers →** a path-mode-only v1 is acceptable **only because**
   their buttons are now **hidden/gated on custom domains** (§4.5 / §12 must-fix
   2); a live-but-dead affordance was not.
5. **Forwarded-host default → off** is right, but the OAuth scheme must **not**
   depend on it (§4.3), and the runbook must lead with the proxy `Host` contract
   (§11).
6. **Cross-host absolute links →** out of Phase 1; the §6 factual error is fixed;
   a `tenant_base_url()` helper is a clean **Phase 2**.
7. **`domain` normalization →** exact-string is **not** enough; add write-time
   normalization + validation **before** Phase 1 (§7 / §12 must-fix 3).

---

## 11. Phased implementation checklist (once the design is settled)

**Phase 1 — resolution + Discord host-local login (Design A).** Ordered so the
must-fixes land before the mechanism that depends on them:
1. **`Tenant.domain` normalization** in `_validate_domain` + `/platform` field
   validation (§7, must-fix 3) — first, because it changes what operators type
   and is the shared contract both resolution and the redirect builder rely on.
2. Wire `get_platform_host()` + effective-host resolution (last-value
   `X-Forwarded-Host` behind `TRUST_FORWARDED_HOST`) into `TenantMiddleware`;
   host-authoritative branch (§3.1); `_cache_by_domain` with separate negative
   cap; rate-limited configured-domain-miss WARNING; startup `PLATFORM_HOST` log.
3. **Single canonical `redirect_uri` builder** (§4.3, must-fix 1) used by both
   OAuth legs, built from the resolved tenant's stored `domain`, `https`-forced;
   do not derive scheme from the request.
4. **Gate/hide the secondary-provider link surfaces on custom-domain hosts**
   (§4.5, must-fix 2).
5. Tests (§9): normalization, host-authoritative precedence, forwarded-host
   last-value, the two-leg redirect_uri identity behind a scheme-rewriting proxy,
   secondary-provider-blocked, referrer, caching; set `PLATFORM_HOST` in the
   harness; keep path mode green.
6. `.env.example` (`TRUST_FORWARDED_HOST`, cross-ref `TRUST_PROXY_FORWARDED_FOR`)
   + deployment/auth docs; **runbook leads with the proxy `Host` contract**, then
   the per-domain Discord redirect-URI registration and DNS/TLS prerequisites.
7. Seed a domain'd tenant (`foo.localhost:8000`) in `scripts/seed_dev.py`; verify
   via `/ui-validation`.
8. Update `features/multitenancy.md` (host mode now live) and this doc's status.

**Phase 2 — scale-out.** Status per item:
- **Design B signed-handoff — DONE.** `application/services/oauth_handoff_service.py`
  mints a `STORAGE_SECRET`-signed token; single-use is enforced by an in-memory
  nonce store (documented single-worker precondition), TTL 30 s, host **and**
  `discord_id` bound, `next` allow-listed (`_safe_next`, rejects protocol-relative
  and auth routes). Entry points: `/oauth/start` (platform host, target-host
  allow-listed against active tenant domains) and `/session/claim` (custom
  domain). Flag: `HOST_OAUTH_MODE=handoff`.
- **`tenant_base_url()` deep-link helper — DONE.** `application/utils/tenant_urls.py`;
  wired into the equipment QR link (points at the tenant's domain when set).
- **Host-native secondary providers — deferred.** Reuse the handoff primitive
  when built; the Phase-1 detour handles them today.
- **Per-tenant canonical-domain 301 — deferred** (re-auth-across-hosts cost; see
  status note at the top).

---

## 12. Adversarial review — round 1 outcome

Method: five independent lenses (routing/ASGI, auth/OAuth/session, security,
ops/rollout, completeness/fact-check), each grounded in the real repo; every
finding then independently verified against the code (default-refute) before a
synthesis pass. 27 findings survived verification. This section is the record;
the fixes are folded into §1–§11 above.

**Verdict.** Architecturally sound and honest about its own weak points, but the
draft was **not implementation-ready**: the recommended Design A `redirect_uri`
mechanism, as first specified, **broke Discord login by default** behind a TLS
proxy, and the Phase-1 scope shipped **live-but-dead OAuth buttons** on custom
domains. Both are fixable within Design A (done above), alongside a missing
`Tenant.domain` normalization contract.

### Must-fix before implementing (all folded in)

1. **One canonical `redirect_uri` builder, built from the resolved tenant's
   stored `domain` — not two request-derived legs.** Merged from four lenses. The
   naïve split derivation (`/login` from `request.url.scheme`, callback from
   `window.location`) fails token exchange behind a TLS-terminating proxy with
   `TRUST_FORWARDED_HOST` off — an outage on the **platform host**, before any
   custom domain exists. Also closes host-header injection by construction. → §4.3.
2. **Gate/hide the secondary-provider link buttons on custom-domain hosts.**
   Challonge / Twitch / racetime / Discord-connect all write CSRF state into the
   host-only cookie and bounce to the platform-host callback, where the custom
   domain's cookie doesn't exist → the link **silently fails** with no error.
   "Deferred" ≠ safe; the affordance must be blocked, not left live. → §4.5, §1.
3. **`Tenant.domain` normalization contract.** Matching is exact-string against a
   verbatim-stored value with only `strip().lower()`; `https://foo.gg`,
   `foo.gg:443`, `foo.gg/`, `foo.gg.`, or `== PLATFORM_HOST` all store fine and
   then **silently never route**. Normalize identically at write- and
   resolution-time; reject at `/platform`. → §7, §3.3.

### Should-address (medium)

- **Host-authoritative precedence** so a custom domain serves exactly one tenant
  (`/t/<other>` 404s there). → §3.1, §10.2.
- **Take the _last_ `X-Forwarded-Host` value**, not the first (append-ordered;
  leftmost is client-controllable). → §3.3, §8.3.
- **Rate-limited WARNING on a configured-domain miss + startup `PLATFORM_HOST`
  log** so a proxy misconfig isn't a silent wrong-surface render. → §3.1.
- **State the real Discord slot budget (~8, not 10)** and a numeric B-migration
  trigger. → §4.2.
- **Cross-reference the two trusted-proxy flags** (`TRUST_PROXY_FORWARDED_FOR`
  exists; `TRUST_FORWARDED_HOST` is new). → §7.
- **§6 factual correction:** equipment QR links already work (tenant-qualified
  path mode); re-audit web-push/DM links individually. → §6.
- **Set `PLATFORM_HOST` in the test harness** (existing tests pass only because
  unknown-host is lenient). → §9.
- **Cap the negative domain cache separately** so a distinct-`Host` flood can't
  evict real positives. → §3.4.
- **Design B nonce store** must be specified if B is ever built (single-worker
  in-memory ties single-use to the single-worker precondition). → §11 Phase 2.

### What held up (confirmed correct — do not relitigate)

- **The OAuth callback runs tenant-less in both modes, and that is fine** — it's
  a plain `@ui.page` whose body runs after `TenantMiddleware` reset the context;
  provision writes a global `User`, audit stamps `tenant=NULL`, `sync_user_roles`
  fans out per-tenant in its own `tenant_scope`. No behavior change. (One-line
  caveat: a *future* tenant-scoped write in the callback body would need an
  explicit scope.)
- **The REST API stays bearer-derived on every host** — `/api` is excluded before
  resolution; "one domain == one tenant" correctly does not extend to it.
- **Forged `Host` is not a cross-tenant data leak** — isolation is enforced by
  `tenant_id` on every query + the leak tests; a forged `Host` only selects which
  community *shell* renders. §8.2 is accurate.
- **Cache poisoning is a documentation concern, not a live leak** — `Host` is
  already the primary cache key and NiceGUI HTML is per-client dynamic; a
  `Vary: Host` note in the runbook suffices.
- **`root_path=''` in host mode, the host-only-cookie "auth per host" invariant,
  and domain-ownership/TLS as non-goals** are correctly reasoned and scoped.

*One verifier agent errored out (StructuredOutput retry cap) on a single
finding's check; 34/35 agents completed. It does not affect the findings above.*
