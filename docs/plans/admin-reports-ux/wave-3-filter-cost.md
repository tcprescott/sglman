# Wave 3 — the cost of changing a filter

**Read [README.md](README.md) first.**

Closes [F2](../../reviews/admin-reports-ux.md#f2--major--a-filter-change-costs-44-s-a-full-navigation-and-your-place-on-the-page).
One filter change on the crew report, instrumented: **4,447 ms wall clock, one
full frame navigation, 28 HTTP requests, and `scrollY 600 → 0`.**

The reload itself stays — [current-state.md](../../current-state.md) records it
as a deliberate deferral (six report bodies wrapped in `@ui.refreshable` plus a
`history.replace` swap, modest reward against real regression risk on an
admin-only surface that works), and that reasoning still holds. **What the
deferral note was missing is the number, and the number says the felt cost is
not the latency — it is losing your place.** On telemetry (3,942 px) and
insights (3,709 px), being thrown to the top is most of the page.

This wave fixes what is felt, cheaply, and leaves the render path alone.

| Task | Fixes | Depends on |
|---|---|---|
| T3.1 | scroll position survives a filter change | — |
| T3.2 | the click is acknowledged instantly instead of 4.4 s later | — |
| T3.3 | re-measure; correct the deferral note with real numbers | T3.1, T3.2 |

**Scope fence:** if you find yourself editing a report *body* to make it
refreshable, stop — that is the change this wave exists to avoid.

---

## T3.1 — Remember where the operator was

**Why.** Every filter handler in all eight reports routes through
`navigate_with_params`
([`shared.py:220`](../../../pages/admin_tabs/reports/shared.py#L220)) →
`ui.navigate.to(reports_url(...))`, which is a real browser navigation. The
browser cannot restore scroll on a URL it has never seen (the URL changes with
every filter), so it lands at 0.

### Files

- `pages/admin_tabs/reports/shared.py`

### Change

Two halves, both in `shared.py`, both keyed by the **report name** so a change
of report starts at the top (which is right — a different report is a different
page, not a moved position):

1. **Record.** `sessionStorage['wiz-report-scroll:<report>'] = window.scrollY`,
   written by a scroll listener installed once per report render, not read at
   navigate time. Reading it inside `navigate_with_params` is the obvious
   implementation and the fragile one: the handler is synchronous, the
   navigation is immediate, and a round-trip to the browser to fetch `scrollY`
   races it.
2. **Restore.** On the next render of the *same* report, scroll back — but not
   before the tables exist. A report body is built server-side and streamed;
   restoring at connect time on a 3,900 px page scrolls a 900 px document.
   Restore inside a short `requestAnimationFrame` loop that retries until
   `document.body.scrollHeight >= y`, capped (~2 s / ~60 frames), then gives up
   silently.

`report_page_shell` ([`shared.py:120`](../../../pages/admin_tabs/reports/shared.py#L120))
is the one place every report passes through, so it is where this hangs — but it
currently receives a *title*, not a report key. Give it the key (its callers are
eight modules and each already knows its own name) rather than deriving one from
the title.

For the client-side hook, **read `nicegui/llms.md` in the installed package for
the current connect-time rule before writing it** — whether the JS can be
emitted during page build or must wait for the client is exactly the kind of
detail that differs between NiceGUI versions, and a guess here fails silently.
The JS must be a **static literal**; `check_markdown_xss` reserves the raw-HTML
and script sinks for literals, and the report key must be passed as data, not
interpolated into the script text.

Dashboard included: it has no filters today (F5, wave 4 gives it some), so it
neither records nor restores until then. Do not special-case it.

### Verify

A one-off Playwright script (this cannot be seen in a screenshot):

1. Open `?report=telemetry`, scroll to ~600 px, change the date filter.
2. After the reload settles, assert `window.scrollY` is within ~50 px of 600.
3. Then switch to `?report=crew` and assert it lands at 0.
4. Repeat at 390×844, where crew is 6,962 px tall and the effect is largest.

Also confirm nothing is written to `sessionStorage` for a report you never
scrolled, and that a second browser tab on a different report does not clobber
the first (that is what keying by report buys — say so in the commit message).

---

## T3.2 — Acknowledge the click

**Why.** 4.4 s of nothing is what makes the reload read as broken, independent
of the scroll reset. The instrumented change made 28 HTTP requests; the operator
sees a stale page with a stale filter value for the whole of it, and a second
click during that window queues a second navigation.

### Files

- `pages/admin_tabs/reports/shared.py`

### Change

In `navigate_with_params`, before navigating: show a determinate-free progress
indicator and stop accepting further filter input. `ui.notify` is the wrong tool
(it stacks and outlives the navigation); a `q-inner-loading`-style overlay on the
page container, or NiceGUI's page-level loading indicator, dies with the page —
which is exactly what is wanted, since the new page will render fresh.

Whatever is chosen must survive being triggered twice: the second call should be
a no-op, not a second overlay.

### Verify

Throttle the network in the Playwright run (or point at a wide date window so
the query is genuinely slow) and confirm: indicator appears within one frame of
the change event, no double navigation on a fast double-change, and no leftover
overlay after the new page renders.

---

## T3.3 — Re-measure, and correct the record

**Why.** F2 exists because the deferral note in `current-state.md` asserted a
trade-off without a number. Leaving the note as-is after changing the felt cost
would repeat the mistake in the other direction.

### Files

- `docs/current-state.md`
- `docs/reviews/admin-reports-ux.md`

### Change

Re-run the audit's own instrumentation (one filter change on the crew report:
wall clock, frame navigations, HTTP requests, scroll before/after) and rewrite
the `current-state.md` bullet to say what is now true: the reload remains, it
still costs ~4.4 s and 28 requests, and it no longer costs the operator their
place. Keep the deferral and its reasoning — this task narrows the note, it does
not delete it.

Update F2 in the audit doc with the after-numbers and mark it closed. (The audit
file is deleted when the last wave merges; until then it must not read as if
nothing has been done.)

### Verify

The numbers in the doc come from a run you did, in this branch, and the
before/after pair is stated as a pair.
