# Render-cost reduction

**Status:** proposed. Continues Phase 1 of
[single-worker-escape-plan.md](single-worker-escape-plan.md), whose first step
(lazy tab rendering) is shipped.

**Why this is still the highest-value workstream:** page render is the app's
admission bottleneck (§1 of the escape plan — one render is ~94 % event-loop CPU,
and the DB is never contended). Every millisecond removed here multiplies across
every replica added later, so this is worth finishing *before* buying cores.

**Where we are:** after lazy tabs *and* the match-table load dedupe (R1), the
tenant home costs **74 ms CPU/render** (down from 289 ms) and admin **~113 ms**,
giving ~13 admissions/second on the home page. That already clears 500 concurrent connections at
a 0.3 s arrival cadence. This plan is about the *crowd* case — 500 people
arriving in 30 seconds rather than 150 — and about the shared shell cost that
every page pays.

---

## 1. Where the remaining time goes

Re-measured after lazy tabs and the load dedupe (R1). The home page is now
**74 ms CPU and 26 queries** per render, so the remaining terms are the page
shell and the default tab:

| Cost | Share of a render | Notes |
|---|---|---|
| Page shell (`render_chrome`) | ≈14 % | Of which `_render_drawer` ≈9 % — one `q-item` per tab, 24 of them on admin, plus the bottom-nav duplicate of the first four. Paid by *every* page. |
| Match table construction | ≈12 % (`_render_tab_panels`, nearly all `_setup_ui`) | 16 inline Vue slot templates + the mobile grid slot. → R2 |
| Repeated user lookups | 6 queries | Same signed-in user resolved several times. → R6 |
| Repeated tenant-by-id | 4 queries | The one `TenantService` lookup that is not cached. → R7 |
| NiceGUI per-element overhead | proportional to element count | `expects_arguments` → `inspect.signature` per handler registration. Framework behavior; only fewer elements reduces it. → R2 |

Note the shell has overtaken the tab content on the home page. That inverts the
pre-lazy ordering, which is why R1 came first.

---

## 2. Work items

### R1 — Re-profile ✅ done

Re-profiled after lazy tabs. Findings, and what came out of them:

- **Three table loads per page render** — the stored tournament and stage
  filters each fired their select's `on_change` during restore, and each handler
  scheduled its own `refresh()`; the page kicked a third explicitly. **Fixed:**
  the view now owns a single ordered initial load. 58 → 26 queries per render,
  home 158 ms → 74 ms CPU. This also closed a race where the first paint could
  ignore a stored filter.
- **Remaining per-render queries (26):** 6 user lookups (R6), 4 identical
  tenant-by-id fetches (R7), 2 tournament fetches, then a long tail of one-offs.
- **Remaining CPU shape:** `render_chrome` ≈ 14 % (of which `_render_drawer`
  ≈ 9 %), `_render_tab_panels` ≈ 12 % (almost all of it the match table's
  `_setup_ui`).

Re-profile again after R2/R3 before doing R4.

### R2 — Match table element count

`theme/tables/match.py` builds 16 inline Vue slot templates, several of which are
per-permission-variant copies of the same markup (the code-quality audit filed
this as §2B: "player/crew Vue templates triplicated per permission variant + again
in grid"). One parameterized template per concern, selected by a prop, instead of
a copy per variant.

This is a **DRY fix with a performance payoff**, and the audit already wanted it —
worth doing on those grounds even if the profile says the win is modest.

*Risk:* the slot templates are client-side and invisible to pytest. Every change
here needs the `/ui-validation` browser loop, and the mobile grid variant needs
checking at 390 px as well as desktop.

### R3 — The Schedule tab's query fan-out

`get_matches_for_display` + `_fetch_watched_ids` behind the default tab. Target
the N+1: prefetch what the row formatter reads rather than resolving per row.
`MatchRepository` already owns prefetch knowledge (`MATCH_PREFETCH`) — the fix
belongs there, not in the view.

Measure queries-per-render before and after; the count is the honest metric, not
local wall time, because loopback Postgres flatters every round trip.

### R4 — Shell cost

Now the **largest single term on the home page** (≈14 %, of which the drawer is
≈9 %) — R1 promoted this from "lower confidence" to a real target. The drawer
renders one `q-item` per tab (24 on admin) plus the bottom-nav duplicate of the
first four, on every page load. Unlike R2/R3 the win applies to *every* page,
including the light ones.

*Note:* ≈9 % is ~6 ms, which is **below the noise floor in §2b** — so this cannot
be validated by timing on the current rig. Either measure it structurally
(element count per render) or batch it with R2 so the combined change clears the
noise. Also note the drawer cannot simply be built lazily: `show-if-above` means
it is genuinely visible on desktop, not just on toggle.

### R6 — The 6 repeated user lookups

`get_user_from_discord_id` resolves the same signed-in user several times per
render (page body, auth checks, the table's watched-ids lookup). A per-request
memo would remove ~5 queries.

**Why this was not taken as a quick win:** the obvious implementation is a
module-level cache, which CLAUDE.md forbids for per-user state and which would
be a genuine cross-user leak here. A correct fix needs request-scoped storage
(`app.storage.client`, or threading the resolved `User` through the call chain)
plus a decision about staleness within a single render. Worth doing, but it is a
design change, not a one-liner.

### R7 — The 4 identical tenant-by-id fetches

`TenantService` caches `get_by_slug`, `get_by_guild`, and `get_by_domain` — but
**not** `get_by_id`, which is the one on the hot path. Four call sites resolve the
same current tenant per render: `pages/home.py` (twice, via `TenantService` and
`FeatureFlagService`) and `theme/base.py` (twice, via `current_community_name`
and `TenantThemeService`). Tenants are global objects, so an id-keyed cache would
not be per-user state and would fit the existing documented pattern.

**Why this was not taken as a quick win — read before implementing.**
`TenantThemeService.set_theme` writes via `TenantRepository.update(...)`
**directly**, bypassing `TenantService._clear_cache()`. Caching `get_by_id`
today would therefore serve a **stale theme** after a save —
`get_current_theme`'s docstring explicitly relies on the read being uncached.
Any implementation must first audit every direct `TenantRepository.update`
caller and route them through an invalidating path. Cheap in isolation, but it
is a cache-invalidation change across three services, and the payoff is ~4
queries (~1–2 ms locally).

### R8 — Regression guard

None of the above stays fixed without a check. Options, cheapest first:

1. **A render-cost test** that asserts an upper bound on queries-per-render for
   the home page (count via a Tortoise query hook). Query count is stable across
   machines; wall time is not, so **do not assert on time** in CI.
2. **A guardrail hook** in the house style (`.claude/scripts/`) that flags a new
   eager `await` of tab content in `theme/base.py`, so the lazy-render property
   is not silently reverted.

Prefer (1) — it catches the N+1 class generally, not just this one instance.

---

## 2b. Measured and rejected — do not re-try these

Each of these looked like a quick win, was implemented or prototyped, measured,
and **produced no demonstrable improvement**. Recorded so the next person does
not spend the same afternoon.

- **`BaseHTTPMiddleware` → pure ASGI.** The stack carries four of them
  (`FunFact`, `SecurityHeaders`, `Auth`, `Tenant`), and Starlette runs the
  downstream app in an anyio task group per middleware per request — a real,
  documented cost. Converting the two header-only ones was implemented in full
  (headers verified byte-for-byte). Result: sequential median **63 ms baseline vs
  71 ms converted** — i.e. no better, with ranges overlapping almost entirely.
  Under a 500-tab burst, **288/500 baseline vs 255/500 converted**. Reverted.
  *If revisited, the candidates worth converting are `Auth` and `Tenant` (which
  run real logic), not the header ones — and only with a measurement rig quieter
  than the one described below.*
- **Raising NiceGUI's `response_timeout`** (default 3.0 s) from the single choke
  point at `middleware/auth.py:192`. When a page build exceeds it, NiceGUI
  cancels the build and *deletes the client*, so a queued visitor gets nothing
  rather than a slow page — which is exactly the burst failure mode. Raising it
  to 20 s gave **304/500 and 219/500** against a baseline of 92, 255, 288/500.
  No signal. Reverted.
- **Disabling TLS on the database connection.** The profile showed heavy
  `asyncio.sslproto` and ~1200 HMAC operations per render, because Debian's
  packaged Postgres enables `ssl=on` with a snakeoil certificate. This is a
  **test-environment artifact**: `postgres:16-alpine` (what `docker-compose.yml`
  runs) ships no server certificate, so production is already un-TLS'd. It also
  means every CPU figure in these plans is slightly **pessimistic** relative to
  the real deployment.

### Measurement noise floor — read before chasing anything small

On the box these numbers were taken (driver and server sharing a host):

- Sequential renders vary **±15 %** run to run (50 renders per sample, 5 samples).
- The 16 tabs/s burst is past the system's knee and is **chaotic**: five runs of
  the identical configuration produced 92, 219, 255, 288 and 304 connections out
  of 500.

**Anything under a ~20 % improvement cannot be validated here.** That is why the
remaining items are structural (fewer elements, fewer queries) rather than
micro-optimizations: only changes large enough to clear the noise are worth
attempting without a dedicated, quiet measurement environment. Prefer
**queries per render** as the primary metric where possible — it is exact and
machine-independent.

---

## 3. Success criteria

- ~~Home render ≤ 90 ms CPU~~ **met** (74 ms). Admin **≤ 90 ms** remains open.
- ~~Queries per home render < 100~~ **met** (26, from 377 pre-lazy). Next target
  **< 20**, which means R6 or R7.
- ~~500 tabs at a 0.15 s ramp with zero failures~~ **met**, and beaten — see the
  measured curve below. Next target: **500 tabs in 30 s (~16/s)**, the burst
  that currently fails.
- `/ui-validation` clean on the schedule, home tabs, and admin at desktop and
  390 px.

### Measured arrival-rate curve (current tree)

500 tabs, varying only the arrival rate. This is the number to move.

| Arrival rate | Ramp | Connected | Render p50 |
|---|---|---|---|
| 3.3/s | 150 s | **500/500** (was 205/500 pre-lazy-tabs) | 81 ms |
| 6.7/s | 75 s | **500/500** | 71 ms |
| 10/s | 50 s | **500/500** | 368 ms |
| 16/s | 30 s | **92/500** ❌ | 4095 ms |

So the sustainable admission ceiling is **~10 tabs/second**, with the cliff
between 10 and 16 — below the ~13.5/s that 74 ms of CPU would suggest, because a
render is not the only work per arrival (socket.io handshake, the post-render
table load, outbox flush). Re-run this curve after each work item; it is the
honest end-to-end measure, and `scripts/loadtest/` reproduces it.

---

## 4. What this plan deliberately does not do

- **It does not add processes or infrastructure.** That is
  [web-worker-split-plan.md](web-worker-split-plan.md) and
  [web-replicas-plan.md](web-replicas-plan.md).
- **It does not touch the DB pool.** `maxsize=5` was measured uncontended
  (`pg_active` ≤ 1 throughout a 500-tab run). Making it configurable is
  hygiene, and belongs with the split, not here.
- **It does not chase NiceGUI's per-element overhead directly.**
  `inspect.signature` per handler is framework behavior; the only lever we hold
  is creating fewer elements.
