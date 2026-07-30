# Admin reports UX — evaluation

**Scope:** the nine report surfaces and their shared shell —
[`pages/admin_tabs/reports/`](../../pages/admin_tabs/reports/) (`dashboard`,
`crew`, `capacity`, `match_ops`, `stream_rooms`, `volunteers`, `telemetry`,
`insights`, `audit`) over
[`shared.py`](../../pages/admin_tabs/reports/shared.py) and `ReportsService` /
`AnalyticsService`.

**Method:** drove all nine against the seeded `default` tenant as `staff_user`,
measuring load time, scroll height, interactive controls in each table body, and
chart count; then instrumented one filter change for frame navigations, HTTP
requests and scroll position. Re-checked three reports in dark mode, over an empty
date window, and at 390×844. Every number below is measured.

**Headline:** these are good reports — the numbers are right, the empty states are
graceful, dark mode themes the charts properly, and every table has a mobile card
view and a CSV export. Two things stand out. **Not one of the nine has a single
button or link inside a table row** — they can all identify work and none of them
can act on it — and the known filter-reload issue costs a measured **4.4 s, a full
page navigation, 28 HTTP requests, and your scroll position**.

---

## The measured shape

| Report | Load | Scroll | Tables | Rows | Row buttons | Row links | Charts | CSV |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| dashboard | 3,420 ms | 1,118 px | 0 | 0 | **0** | **0** | 0 | no |
| crew | 3,438 ms | 1,800 px | 2 | 21 | **0** | **0** | 0 | yes |
| capacity | 4,196 ms | 2,562 px | 1 | 25 | **0** | **0** | 2 | yes |
| match_ops | 3,370 ms | 1,809 px | 2 | 23 | **0** | **0** | 0 | yes |
| stream_rooms | 3,407 ms | 1,154 px | 1 | 3 | **0** | **0** | 2 | yes |
| volunteers | 3,356 ms | 1,841 px | 1 | 25 | **0** | **0** | 0 | yes |
| telemetry | 3,540 ms | 3,942 px | 4 | 76 | **0** | **0** | 0 | yes |
| insights | 3,417 ms | 3,709 px | 3 | 8 | **0** | **0** | 8 | yes |
| audit | 3,550 ms | 2,950 px | 1 | 50 of 124 | **0** | **0** | 0 | yes |

One filter change (Tournament, on the crew report), instrumented:

| | Measured |
|---|---|
| Wall clock | **4,447 ms** |
| Frame navigations | **1** (a full page load) |
| HTTP requests | **28** |
| Scroll position | **600 → 0** |
| URL | rewritten with the full parameter set |

Mobile, 390×844: **no horizontal body overflow on any report checked**, no
oversized table children, and the mobile grid renders (21 cards on crew, 8 on
insights). Vertical cost is the trade: crew becomes **6,962 px**.

Dark mode: `body--dark` applied, and all eight insights charts re-theme — dark
plot backgrounds, legible axes, themed series colours.

Empty window (`insights` over 2020-01-01 → 2020-01-02): KPI cards read `0` and
`—` with captions (`0 unique people`, `of 0 in window`), and each chart says
*"No crew activity in the selected window."* Nothing broke, nothing rendered as
empty axes.

---

## Findings, ranked

### F1 — Major · Nine reports, zero actions

Measured across every report: `row_buttons=0`, `row_links=0`. The reports find
real work and offer no route to it:

| What a report shows | Where the fix lives |
|---|---|
| `Understaffed shifts — 57 shift(s) need 57 more volunteer(s)` (volunteers) | Admin → Vol. Schedule, per day, per shift |
| `Peak players 14 / 12` — over the configured ceiling (dashboard) | Admin → Schedule, or Settings |
| Pending crew and `Coverage gap` per match (crew) | the crew cell of the Schedule board |
| Matches with no result / needs review (match_ops) | the Schedule board's review queue |

Every one requires the operator to memorise an id and navigate. The shell already
has `clicked_row` ([`shared.py:258`](../../pages/admin_tabs/reports/shared.py#L258))
and the app already has a deep-linkable schedule board, so the missing piece is a
row click that carries the id — not new machinery. The
[crew audit](crew-signup-ux.md#f2--critical--nothing-tells-anyone-that-a-signup-is-waiting)
found this from the other side: the only surface that can see pending crew work is
the one that cannot approve it.

### F2 — Major · A filter change costs 4.4 s, a full navigation, and your place on the page

[current-state.md](../current-state.md) records the reload as a known,
deliberately-deferred issue; this is the number the note was missing. The part
that makes it feel broken is not the latency but the **scroll reset**: measured
`scrollY 600 → 0`, so an operator narrowing a filter while looking at a table two
screens down is thrown back to the top of a 1,800–3,900 px page every time. On
telemetry (3,942 px) and insights (3,709 px) that is most of the page.

The deferral reasoning (wrap six report bodies in `@ui.refreshable`, swap to
`history.replace`, modest reward, real regression risk) still holds for the
latency. The scroll reset is cheaper to fix than the reload — preserving and
restoring `scrollY` across the navigation would remove most of the felt cost
without touching the render path.

### F3 — Minor · Insights' default window is much wider than the data, so every chart is one spike at the right edge

Measured on the default view: a ~90-day window bucketed weekly, with 13 empty
buckets and everything in the last one. The page has range shortcuts
(`Last 30d` / `Last 90d` / `Last year`) and the bucket select, so the operator can
fix it — but the default should be derived from the data's extent (the crew report
already defaults to the **event window**, `2026-07-29 → 2026-07-31`, which is the
right instinct).

### F4 — Minor · The audit report shows 50 of 124 entries with the count in the header

`124 entries` sits above a table paginated to 50 with no indication that what you
are reading is a page. The CSV export is the way to get everything, which is fine —
but the count and the page size should not silently disagree.

### F5 — Minor · The dashboard is the only report with no export and no filters

It renders KPI cards over a window derived from the event dates
(`Window: 2026-07-29 → 2026-07-31 (US/Eastern)`) with no date control and no CSV.
That is defensible for a landing page, but `Peak players 14 / 12` — a number over
its own ceiling — is exactly the KPI an operator will want to widen or narrow, and
there is no control to do it.

---

## What works

- **Every zero state is deliberate.** KPIs render `0` and `—` with explanatory
  captions; charts say *"No crew activity in the selected window."* This is the
  part of a reporting surface that usually rots, and it is right in all nine.
- **Dark mode is genuinely handled** — `themed_chart_option` re-themes all eight
  insights charts, not just the page chrome.
- **Mobile is respected**: no horizontal body overflow anywhere measured, every
  table carries `enable_mobile_grid`, and cards render at 390 px.
- **Filter shortcuts where they matter most** — capacity offers
  `Whole event / Wed 07-29 / Thu 07-30 / Fri 07-31`, insights offers
  `Last 30d / Last 90d / Last year`. Both remove the two-date-picker dance.
- **CSV on eight of nine**, built from the same column definitions the table uses.
- **The crew report's default window is the event window**, not an arbitrary
  rolling range.
- **Composite metrics explain themselves** — *"Composite 0–100 score from
  completion, on-time, crew coverage, and duration adherence"* sits directly under
  the tournament-health chart.

## Not covered

CSV *contents* (only the presence of the export was checked), the audit report's
`parse_details` against unusual `details` shapes, `paginated_event_log` at large
scale, and a tournament-admin-only role pass (all measurements are `staff_user`).
