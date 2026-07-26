# Render-cost reduction

**Status:** proposed. Continues Phase 1 of
[single-worker-escape-plan.md](single-worker-escape-plan.md), whose first step
(lazy tab rendering) is shipped.

**Why this is still the highest-value workstream:** page render is the app's
admission bottleneck (§1 of the escape plan — one render is ~94 % event-loop CPU,
and the DB is never contended). Every millisecond removed here multiplies across
every replica added later, so this is worth finishing *before* buying cores.

**Where we are:** the tenant home costs **132 ms CPU/render**, admin **116 ms**,
giving ~7.6 admissions/second. That already clears 500 concurrent connections at
a 0.3 s arrival cadence. This plan is about the *crowd* case — 500 people
arriving in 30 seconds rather than 150 — and about the shared shell cost that
every page pays.

---

## 1. Where the remaining time goes

The §1.3 profile was taken before lazy tabs. It needs re-taking, because the
proportions have moved: removing 8 of 9 tab bodies leaves the shell and the
default tab as the dominant terms. **Step 1 of this plan is to re-profile**, not
to act on stale attribution.

What the pre-lazy profile still tells us, because these costs did not go away —
they are simply now a larger share of a smaller number:

| Cost | Evidence | Notes |
|---|---|---|
| Match table construction | `theme/tables/match.py` `_setup_ui` 0.427 s per 10 renders | 16 inline Vue slot templates + the mobile grid slot. Paid by the default Schedule tab on the home page. |
| N+1 query fan-out | 377 `queryset._execute` calls per single render | Locally ~90 ms; on a network-attached DB every round trip is charged again. Some of this belonged to the eager tabs and is already gone — re-measure. |
| NiceGUI per-element overhead | `expects_arguments` → `inspect.signature` ~1509×/render | A direct function of element count. Only fewer elements reduces it. |
| Page shell | header, drawer (one `q-item` per tab), footer nav, theme load | Paid by every page including the light ones. The drawer still enumerates all 24 admin tabs. |

---

## 2. Work items

### R1 — Re-profile (do first, blocks the rest)

Re-run `scripts/loadtest/profile_render.py` against the current tree for the
tenant home **and** `/t/default/admin`. Record the new top-10 by cumulative time
in this doc. Do not start R2–R4 before this: the remaining ordering is a
hypothesis until re-measured.

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

Lower confidence — measure before touching. The drawer renders one `q-item` per
tab (24 on admin) plus the bottom-nav duplicate of the first four. If the shell
turns out to be a meaningful share of a now-116 ms admin render, the drawer is
the place to look.

### R5 — Regression guard

None of the above stays fixed without a check. Options, cheapest first:

1. **A render-cost test** that asserts an upper bound on queries-per-render for
   the home page (count via a Tortoise query hook). Query count is stable across
   machines; wall time is not, so **do not assert on time** in CI.
2. **A guardrail hook** in the house style (`.claude/scripts/`) that flags a new
   eager `await` of tab content in `theme/base.py`, so the lazy-render property
   is not silently reverted.

Prefer (1) — it catches the N+1 class generally, not just this one instance.

---

## 3. Success criteria

- Home render **≤ 90 ms CPU** and admin **≤ 90 ms** (≈11 admissions/s), or a
  documented finding that the remaining cost is irreducible without a NiceGUI
  change.
- Queries per home render **< 100** (from 377 pre-lazy; re-baseline in R1).
- 500 tabs connect at a **0.15 s ramp** (75 s) with zero failures — twice the
  arrival rate the shipped state handles.
- `/ui-validation` clean on the schedule, home tabs, and admin at desktop and
  390 px.

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
