# Admin reports UX — implementation plan

Follow-up to [`docs/reviews/admin-reports-ux.md`](../../reviews/admin-reports-ux.md).
That document is the *evidence* — nine reports driven against the running app,
every number measured. This directory is the *work*. Read the finding (F-number)
a task references before implementing it.

**Read this file completely before starting any task.** It carries the design
decisions, the ground rules and the verification loop that the wave files do not
repeat.

## Wave files

| Wave | File | Theme | Closes | Migration? |
|---|---|---|---|---|
| 1 | [wave-1-destinations.md](wave-1-destinations.md) | Make the surfaces a report wants to link to accept a deep link — and seed the roles that prove the links are gated | prerequisite for F1 | no |
| 2 | [wave-2-row-actions.md](wave-2-row-actions.md) | The headline: every report that identifies work gets a route to the surface that fixes it | **F1** | no |
| 3 | [wave-3-filter-cost.md](wave-3-filter-cost.md) | Stop a filter change throwing the operator back to the top of a 3,900 px page | **F2** | no |
| 4 | [wave-4-report-fixes.md](wave-4-report-fixes.md) | Insights' default window, the audit report's page/count disagreement, the dashboard's missing window control | **F3, F4, F5** | no |

Wave 1 is plumbing with no visible change; **wave 2 is the point of this plan**
and the audit's headline finding. Waves 3 and 4 are independent of each other
and of wave 2 — if only one more wave gets done after 2, do wave 3, because F2
is felt on every single filter change.

Do not start wave N+1 until wave N is merged. Wave 2 depends on wave 1's URL
plumbing and on wave 1's seeded roles; waves 3 and 4 depend on nothing but a
merged wave 1 (they touch `shared.py`, which wave 1 also edits).

Within a wave, tasks list their own `Depends on`. Tasks with no dependency can
be done in any order.

## The workflow being served

An operator opens Reports to answer *"what needs my attention?"*, and the answer
is always a piece of work that lives somewhere else:

1. *57 shifts need 57 more volunteers* → assign someone, on Admin → Vol. Schedule.
2. *Coverage gap on match 412* → approve the pending commentator, in the crew
   cell of the Schedule board.
3. *Nine matches Finished with no result* → the Schedule board's review queue.
4. *Peak players 14 / 12* → widen the window, or move a match.

Today every one of those ends with the operator memorising an id and navigating
by hand: measured `row_buttons=0`, `row_links=0` across all nine reports. The
loop this plan closes is **notice → act**, not *notice → re-find*.

## Design decisions

Fixed, and agreed before the waves were written. **If a task seems to contradict
one of these, the task is wrong — stop and ask.**

- **Reports link; they do not act.** No approve / assign / confirm control goes
  inside a report. A report row carries an **id** to the surface that already
  owns that action, with that surface's own authorization. Duplicating a
  mutation into nine read-only surfaces means duplicating its auth gate nine
  times, and the match-ops audit is the record of what happens when a
  presentation-layer boolean drifts from the service's gate.
- **Navigation is an explicit control, never the row click.** Four reports
  already spend `row-click` on *filtering*: crew's contribution table
  ([`crew.py:194`](../../../pages/admin_tabs/reports/crew.py#L194)), the audit
  log ([`audit.py:142`](../../../pages/admin_tabs/reports/audit.py#L142)),
  telemetry's leaderboards
  ([`telemetry.py:152`](../../../pages/admin_tabs/reports/telemetry.py#L152)) and
  stream rooms' summary table. Those meanings stay. A drill-*out* is a link or
  an icon button in its own cell, so one click never means two things.
- **Deep-link state travels in the query string.** The admin page already
  declares the reports' params and hands them to the Reports tab as
  `reports_kwargs` ([`pages/admin.py:38`](../../../pages/admin.py#L38),
  [`:100`](../../../pages/admin.py#L100)). Wave 1 extends exactly that
  mechanism to the Schedule and Vol. Schedule tabs. Do **not** invent per-tab
  session state, and do not smuggle the id through `app.storage`.
- **A link is rendered only when its destination will admit the viewer.** The
  Reports tab admits staff, any tournament admin **and** any crew coordinator
  ([`pages/admin.py:163`](../../../pages/admin.py#L163)); Vol. Schedule needs
  STAFF or VOLUNTEER_COORDINATOR *and* `FeatureFlag.VOLUNTEERS`
  ([`pages/admin.py:147`](../../../pages/admin.py#L147)). CLAUDE.md's rule is
  explicit: never offer a link the gate will reject. Every link in wave 2 is
  resolved against the same predicate its destination tab uses.
- **A deep link filters; it does not open a dialog.** `?match_id=412` narrows
  the Schedule board to that match and says so. It does not auto-open the match
  dialog: a modal that appears because you followed a link is a surprise, and
  *which* dialog you wanted depends on why you came (crew cell, result, stream
  room).
- **The filter reload stays.** [current-state.md](../../current-state.md)
  records the `ui.navigate.to` reload as a deliberate deferral, and that
  reasoning still holds. Wave 3 removes the *felt* cost (the scroll reset), not
  the render path. **Rewriting report bodies as `@ui.refreshable` is out of
  scope for this plan** — if it is ever done, it is its own change with its own
  regression budget.
- **No per-tenant feature flag for this work.** It changes surfaces that already
  exist; flags are for deliberately-gated subsystems. One flag *does* get
  applied here — `FeatureFlag.VOLUNTEERS`, to the Volunteer Coverage report that
  currently ignores it (wave 2, T2.4) — but that is enforcing an existing flag,
  not adding one.

## Ground rules

Everything in [CLAUDE.md](../../../CLAUDE.md) applies. The parts these tasks
hit:

**Three-layer pattern.** Presentation (`pages/`, `theme/`) → Service
(`application/services/`) → Repository → Models. These reports are presentation
over services; `enforce_architecture.py` blocks a repository import from a page.
Wave 4's data-extent lookup is **aggregation, so it goes in `AnalyticsService`**,
not in `insights.py` — the reports feature doc states the rule
(*"Aggregation always happens in a service, never in the page"*) and it is the
easiest one to break while "just" computing a default date.

**Tenant scoping.** Nothing here reads a model directly; every number comes from
a service. A URL is tenant-relative: build links the way
[`reports_url`](../../../pages/admin_tabs/reports/shared.py#L63) does —
root-relative, no `/t/<slug>` prefix — because NiceGUI derives the client's URL
prefix from the page's `root_path` (see
[`middleware/tenant.py:95`](../../../middleware/tenant.py#L95)). **Never
hand-build a `/t/<slug>` prefix**, and verify one link by clicking it in a
`/t/default` session before trusting the whole set.

**Feature flags.** Gating is two obligations and UI-only gating is not gating:
hide it at the entry surface **and** enforce it in the owning service
(`@requires_feature`). T2.4 does both for the volunteer report;
`check_feature_flag_gating.py` and
`tests/test_feature_flag_enforcement.py` enforce the pair.

**Errors.** Services raise `ValueError`; presentation catches and notifies. A
`FeatureDisabledError` *is* a `ValueError` subclass path — a report body that
calls a newly-gated service must not blow up for a tenant without the flag; the
report should not be reachable at all (that is why T2.4 gates the card, the
handler and the service together).

**NiceGUI.** `background_tasks.create`, never `asyncio.create_task`. Capture
`context.client` before a background task that touches UI and restore it with
sync `with client:`. No module-level per-user state — the report modules are
imported once and shared by every operator in every tenant.

**Mobile.** Every `ui.table` gets its card view via `enable_mobile_grid`
([`theme/tables/mobile_grid.py:52`](../../../theme/tables/mobile_grid.py#L52)),
and all nine reports already comply. **A row action added to a desktop cell slot
is invisible on a phone unless it is also passed as `actions=` (or a
`field_slots=` override) to `enable_mobile_grid`** — that is the single most
likely way wave 2 half-ships. `check_table_grid.py` enforces the grid's
existence, not the parity of your new button; the 390×844 screenshot is what
catches it.

**Audit + events.** Reports are read-only: **no new audit rows and no new
`EventType` members anywhere in this plan.** The one telemetry write that exists
(`report.viewed`,
[`reports/__init__.py:35`](../../../pages/admin_tabs/reports/__init__.py#L35))
stays as it is.

**File length.** `check_file_length.py` advises over 800 lines.
`shared.py` is 340 and gains helpers in three of the four waves —
check it before adding, and split (`reports/links.py`) rather than grow it past
the threshold.

## Verification loop

```bash
bash scripts/setup_env.sh                      # once per environment
nohup ./start.sh dev > /tmp/app.log 2>&1 &     # wait for "Application startup complete"
poetry run python scripts/seed_dev.py
```

Reports live at `/t/default/admin/reports?report=<key>`; a bare `/admin` 404s.

**Drive it as more than `staff_user`.** Every measurement in the audit was taken
as `staff_user`, and it says so under *Not covered*. Wave 2's links are gated on
predicates `staff_user` always satisfies, so **staff alone cannot verify wave 2**
— that is what T1.1 seeds `cc_user` (crew-coordinator only) and `vc_user`
(volunteer-coordinator only) for. The reports themselves are reachable by all
three.

```bash
cat > /tmp/check.json <<'JSON'
{
  "loginAs": "cc_user",
  "tenant": "default",
  "outDir": "/tmp/ui-check",
  "targets": [
    { "name": "crew", "path": "/admin/reports?report=crew", "selector": ".q-table" }
  ]
}
JSON
NODE_PATH=$(npm root -g) node scripts/ui_smoke.js /tmp/check.json
```

Add `"viewport": {"width": 390, "height": 844}` at the config top level for the
card layout — the audit's mobile numbers were taken at 390×844, so re-measure
there. Anything needing a click (following a link, changing a filter and
checking the scroll position) needs a one-off Playwright script; see the
[`ui-validation`](../../development.md) skill for the login snippet.

```bash
poetry run pytest                 # whole suite, parallel
poetry run pytest -n0 -k volunteer_coverage
scripts/ui_flag_sweep.sh          # flags-off sweep — required by T2.4
```

## Definition of done for every task

1. Implemented in the files named, at the layer named.
2. `poetry run pytest` green.
3. The task's own tests exist **and fail without the change** — say so if a test
   cannot meet that bar and why. Note that there is no `tests/pages/`: report
   bodies are verified in the browser, and what goes in pytest is the *service*
   behaviour behind them (`tests/services/test_reports_service.py`,
   `test_analytics_service.py`, `tests/test_feature_flag_enforcement.py`).
4. The affected report renders at 1500 px **and** 390 px, verified by
   screenshot, with no new console errors — and any link added is **followed**,
   not merely seen.
5. Docs named in the task updated.
6. Committed with a message describing the behaviour change, not the diff.

If a task turns out to be wrong or blocked, **finish the rest of its wave and
say explicitly what you left out and why.** Do not silently narrow scope.

## When this directory is finished

`docs/README.md`: *design records are not kept after they ship.* Delete each
wave file as its wave merges; when the last one lands, delete this directory
**and** [`docs/reviews/admin-reports-ux.md`](../../reviews/admin-reports-ux.md),
remove both rows from the "Work in flight" table in
[`docs/README.md`](../../README.md), and drop the reports audit's row and its
`F1` citation from
[`docs/reviews/README.md`](../../reviews/README.md) — including the
*"Discovery and action live on different pages"* cross-cutting theme, which this
plan exists to retire.

The behaviour must land in the feature docs:
[`docs/features/admin-reports.md`](../../features/admin-reports.md) (the
drill-down contract and which params each tab accepts) and
[`docs/reference/frontend.md`](../../reference/frontend.md#reports-subsystem-pagesadmin_tabsreports)
(the shared link helper and the mobile-card mirror). Git history holds the
rationale.
