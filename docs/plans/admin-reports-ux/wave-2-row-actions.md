# Wave 2 — nine reports, and a route out of each

**Read [README.md](README.md) first.** This wave closes
[F1](../../reviews/admin-reports-ux.md#f1--major--nine-reports-zero-actions), the
audit's headline: measured across every report, `row_buttons=0` and
`row_links=0`. The reports find real work and offer no route to it.

**Depends on wave 1 being merged** — every link here targets a param wave 1
taught a tab to accept, and every gating check here needs `cc_user` / `vc_user`
to be verifiable at all.

| Task | Report | Links to | Depends on |
|---|---|---|---|
| T2.1 | — | the shared link cell, desktop **and** card | — |
| T2.2 | crew | Schedule board, focused on the match | T2.1 |
| T2.3 | match_ops | Schedule board (match; review queue) | T2.1 |
| T2.4 | volunteers | Vol. Schedule at that day — **and the flag gate the report is missing** | T2.1 |
| T2.5 | capacity, stream_rooms | Schedule board, focused on the match | T2.1 |
| T2.6 | dashboard | the report that explains each KPI; stop offering Telemetry to non-staff | — |
| T2.7 | audit, telemetry, crew | make the existing row-click *say* it filters | T2.2 |

The wave is done when the four rows of F1's table each have a working route, and
no operator is offered a link that refuses them.

---

## T2.1 — One link cell, and its card mirror

**Why.** Six reports need the same control. Written six times it will be written
six slightly different ways, and at least one will be invisible on a phone: the
audit measured every report's mobile grid rendering (21 cards on crew, 8 on
insights), and `enable_mobile_grid` builds its card body from the **columns**,
skipping the `actions` column entirely
([`theme/tables/mobile_grid.py:68`](../../../theme/tables/mobile_grid.py#L68)).
A `body-cell-*` slot added to a desktop table simply does not exist in the card.

### Files

- `pages/admin_tabs/reports/shared.py`

### Change

Add one helper — `drill_column()` / `drill_slot()`, name it as you like, but it
must produce **both halves in one call**:

1. the column dict to append to the table's `columns`,
2. the Vue `body-cell-<name>` slot emitting a link (a `q-btn` with
   `icon="open_in_new"` and a `flat dense` look, matching the existing
   `csv_export_button` idiom at
   [`shared.py:217`](../../../pages/admin_tabs/reports/shared.py#L217)),
3. and the `actions=` string for `enable_mobile_grid`, so the same control lands
   in the card footer.

The href is built per row from the row dict — pass the helper a callable
`row -> url` and let it template the value into the row before render (add the
url as a plain field on the row dict; a Vue slot can then read
`props.row.drill_url`). **Do not** build hrefs by string-concatenating inside
the Vue template.

Two constraints that are not negotiable:

- **Rendered only when a predicate says so.** The helper takes `enabled: bool`;
  when false it adds neither column nor slot — not a disabled button. A control
  that is present and refuses is exactly the shape the match-ops audit found 37
  of.
- **`@click.stop`.** Three of these tables already have a row-click that means
  *filter* (see T2.7 and the README's design decisions). Without `.stop`, one
  click both navigates and filters. The existing details cell in
  `_EVENT_LOG_DETAILS_CELL`
  ([`shared.py:277`](../../../pages/admin_tabs/reports/shared.py#L277)) already
  does this — copy that pattern.

### Verify

Not verifiable alone; it ships with T2.2. But before moving on, confirm at
390 px that the card footer shows the control on a table that has one — that
single screenshot is what proves the whole wave is not desktop-only.

---

## T2.2 — Crew coverage → the match, on the board

**Why.** F1's third row. The crew report is the only surface that can *see* a
`Coverage gap` or a pending signup; the
[crew audit](../../reviews/crew-signup-ux.md#f2--critical--nothing-tells-anyone-that-a-signup-is-waiting)
found the same wall from the other side — the surface that can approve crew
cannot find the work. The approval control lives in the crew cell of the
Schedule board.

### Files

- `pages/admin_tabs/reports/crew.py`

### Change

On the **Coverage by match** table
([`crew.py:142`](../../../pages/admin_tabs/reports/crew.py#L142)) — whose rows
already carry `match_id` — add the T2.1 drill column, linking to
`admin_url('schedule', match_id=row['match_id'])`.

Leave the **Contribution by person** table's `row-click` alone: it filters both
tables to that person ([`:177`](../../../pages/admin_tabs/reports/crew.py#L177))
and that is a good behaviour the audit did not fault.

**Gate:** the Schedule tab admits staff, tournament admins and crew coordinators
([`pages/admin.py:118`](../../../pages/admin.py#L118)) — the same three
predicates that let someone see this report. Resolve them with `AuthService` the
way `pages/admin.py` does, once at the top of `crew_page`, and pass the result
to the helper. Do not reimplement the predicate inline per row.

### Verify

- As `staff_user`: a coverage row with `GAP` links to the board, the board shows
  that match only, the crew cell is right there.
- **As `cc_user`**: the link is present (a crew coordinator has the Schedule
  tab) and following it works.
- 390 px: the link is in the card footer, not lost off the right edge.
- The audit's measurement was `row_buttons=0, row_links=0` — re-run whatever
  counted that (or count by hand) and put the new number in the commit message.

---

## T2.3 — Match Operations → the board, including the review queue

**Why.** F1's fourth row: *matches with no result / needs review* are found here
and fixed on the board, which already has a purpose-built review queue
([`admin_schedule.py:60`](../../../pages/admin_tabs/admin_schedule.py#L60) —
flagged / no-result / awaiting-confirmation chips and a **Show only these**
button).

### Files

- `pages/admin_tabs/reports/match_ops.py`

### Change

- **Matches** table ([`match_ops.py:130`](../../../pages/admin_tabs/reports/match_ops.py#L130)):
  drill column → `admin_url('schedule', match_id=row['match_id'])`.
- **Per-tournament aggregates** ([`:97`](../../../pages/admin_tabs/reports/match_ops.py#L97)):
  a link that stays *inside* reports — re-filter this report to that tournament
  (`reports_url('match_ops', tournament_id=…, start=…, end=…)`). The board takes
  no tournament param and wave 1 deliberately did not add one; a report-internal
  drill-down is the honest option and needs no new plumbing.
- Do **not** add a "go to review queue" button that presets the board's state
  filter. The board's own queue already offers `Show only these`, and wave 1's
  T1.2 explicitly deferred a `board_state` param. If it turns out to be wanted,
  it is a follow-up with its own param, not a reuse of `state`.

**Gate:** same three predicates as T2.2 for the board link. The report-internal
link needs no gate — anyone reading this report can already read it filtered.

### Verify

Follow a `Finished` match's link and confirm the focused board shows it **with
its review-queue chips**; a `Confirmed` match's link must also land on a visible
row (that is what T1.3's `default_state_filter` handling is for — if it does
not, T1.3 is wrong, not this task).

---

## T2.4 — Volunteer coverage → the day that needs staffing, and the flag this report ignores

**Why.** Two things, and they must ship together.

**The link.** F1's first row: `57 shift(s) need 57 more volunteer(s)`
([`volunteers.py:50`](../../../pages/admin_tabs/reports/volunteers.py#L50)) is
the most actionable sentence in the whole reports section and it goes nowhere.

**The gate.** `FeatureFlag.VOLUNTEERS` declares
`application/services/volunteer/` as its enforced package
([`application/feature_flags.py:143`](../../../application/feature_flags.py#L143)).
Every other entry surface honours it: the REST router is mounted behind
`require_feature(FeatureFlag.VOLUNTEERS)`
([`api/__init__.py:67`](../../../api/__init__.py#L67)), the MCP tool declares
`feature=FeatureFlag.VOLUNTEERS`
([`mcpserver/tools/volunteers.py:94`](../../../mcpserver/tools/volunteers.py#L94)),
and both Vol. tabs check `FeatureFlag.VOLUNTEERS in live`
([`pages/admin.py:147`](../../../pages/admin.py#L147)). **The Volunteer Coverage
report checks nothing** — neither `_REPORT_HANDLERS`
([`reports/__init__.py:29`](../../../pages/admin_tabs/reports/__init__.py#L29))
nor the dashboard card
([`dashboard.py:50`](../../../pages/admin_tabs/reports/dashboard.py#L50)) — and
`VolunteerScheduleService.coverage`
([`volunteer_schedule_service.py:325`](../../../application/services/volunteer/volunteer_schedule_service.py#L325))
carries no `@requires_feature`. So a community that has never enabled volunteer
scheduling gets a Volunteer Coverage card, opens it, and reads volunteer data.
Linking that page to a tab that does not exist for them would make a latent
inconsistency into a visible dead end.

### Files

- `pages/admin_tabs/reports/volunteers.py`
- `pages/admin_tabs/reports/dashboard.py`
- `pages/admin_tabs/reports/__init__.py`
- `application/services/volunteer/volunteer_schedule_service.py`
- `tests/test_feature_flag_enforcement.py`

### Change 1 — enforce the flag

Add `@requires_feature(FeatureFlag.VOLUNTEERS)` to
`VolunteerScheduleService.coverage`. Both other callers are already gated, so
this changes no working behaviour — it closes the page path. Add a test beside
the existing per-flag cases in `tests/test_feature_flag_enforcement.py`:
`coverage()` on a `bare_tenant` raises.

Then hide the surface: drop `'volunteers'` from `_REPORT_HANDLERS` and the card
from `REPORT_CARDS` when the flag is not live. `FeatureFlagService().enabled_flags()`
is one query and the dashboard already runs several awaits — read it once in
`reports_page` and pass it down, rather than calling `is_enabled` in three
modules. An unknown `report` already falls back to the dashboard
([`reports/__init__.py:61`](../../../pages/admin_tabs/reports/__init__.py#L61)),
so removing the handler gives a flag-off tenant the right behaviour for free.

### Change 2 — the link

Rows are built from `coverage` at
[`volunteers.py:53`](../../../pages/admin_tabs/reports/volunteers.py#L53) and
keep only a *formatted* `starts_at`. Add the Eastern date as a field
(`to_eastern(r['starts_at']).date().isoformat()` — via
`application/utils/timezone.py`, never a naive `.date()`) and link
understaffed rows to `admin_url('vol-schedule', day=row['day'])`.

**Gate:** `AuthService.can_manage_volunteers` (the same predicate
`admin_volunteers_page` itself checks at
[`admin_volunteers.py:37`](../../../pages/admin_tabs/admin_volunteers.py#L37)),
**and** the flag. A crew coordinator reading this report gets the numbers and no
link — which is correct, and is the case `cc_user` exists to prove.

Also give the *Understaffed shifts* summary card a link to the first
understaffed day, so the headline sentence itself is actionable, not only the
table rows.

### Verify

- `scripts/ui_flag_sweep.sh` — **required for this task**, not optional.
- Turn `VOLUNTEERS` off for `default` (`scripts/set_feature_flags.py`): the
  Reports dashboard shows no Volunteer Coverage card, and
  `?report=volunteers` falls back to the dashboard rather than erroring.
- Turn it back on. As `vc_user`: links present and followed, landing on the
  right day. As `cc_user`: numbers present, **no links**.
- `poetry run pytest -n0 -k volunteer` and the API tests
  (`tests/api/test_volunteers.py`) — the router is already gated, so a
  regression there means the decorator went somewhere it should not have.

---

## T2.5 — Capacity and Stream Rooms → the match

**Why.** Both reports already put match ids in front of the operator and both
already spend a click on something else. Capacity's *Top 5 peak times* drill-down
renders a per-instant match table
([`capacity.py:214`](../../../pages/admin_tabs/reports/capacity.py#L214)) —
`Peak players 14 / 12` (F1's second row) is unfixable without knowing which
matches make the peak, and this is the table that says so. Stream Rooms' room
drill-down renders the room's matches
([`stream_rooms.py:161`](../../../pages/admin_tabs/reports/stream_rooms.py#L161)).

### Files

- `pages/admin_tabs/reports/capacity.py`
- `pages/admin_tabs/reports/stream_rooms.py`

### Change

Add the T2.1 drill column to both match tables, keyed on `match_id`, gated on
the same three Schedule-tab predicates as T2.2.

Leave the stream-room summary table's `row-click` alone — it drills into a
single room ([`stream_rooms.py:135`](../../../pages/admin_tabs/reports/stream_rooms.py#L135))
and that is the right meaning. Leave the capacity forecast table alone too: its
`match_ids` column is a plain list of ids with no single target, and turning a
comma-joined string into N links is a worse control than the peak-time
drill-down that already exists.

### Verify

Both at 1500 px and 390 px; follow one link from each.

---

## T2.6 — The dashboard: KPIs that lead somewhere, and one card that should not be there

**Why.** Two separate problems on one page.

`Peak players 14 / 12` renders in `negative` colour
([`dashboard.py:129`](../../../pages/admin_tabs/reports/dashboard.py#L129)) —
the app shouting that a number is over its ceiling — and the card is inert. Same
for `Stream candidate coverage` at `< 50%`. Each KPI is computed from exactly
one report's data (`forecast` → capacity, `coverage` → crew, `ops` →
match_ops), so the destination is unambiguous.

And `REPORT_CARDS` offers **Engagement Telemetry** to everyone with the Reports
tab, while `telemetry_page` refuses a non-staff viewer with a red label
([`telemetry.py:51`](../../../pages/admin_tabs/reports/telemetry.py#L51)). A
tournament admin or crew coordinator is invited to a page that tells them off.
The card even says *"Staff only"* in its own description
([`dashboard.py:67`](../../../pages/admin_tabs/reports/dashboard.py#L67)) —
which is the code admitting the gate belongs one level up.

### Files

- `pages/admin_tabs/reports/dashboard.py`

### Change

- Make `kpi_card` accept an optional `href` (in
  [`shared.py:244`](../../../pages/admin_tabs/reports/shared.py#L244)) and wire
  the four dashboard KPIs to `reports_url('capacity' | 'crew' | 'match_ops', …)`,
  carrying the dashboard's own event window as `start`/`end` so the destination
  opens on the same window the number was computed over. A KPI that links to a
  differently-scoped report is worse than one that does not link.
- Filter `REPORT_CARDS` by viewer: telemetry only for staff (`AuthService.is_staff`,
  which is what `_is_staff` in `telemetry.py` resolves), volunteers only when the
  flag is live (T2.4 — do it in one place if both tasks land together).

Keep the cards' `cursor-pointer` class honest: today the whole card looks
clickable and only the *"Open report →"* link is
([`dashboard.py:168`](../../../pages/admin_tabs/reports/dashboard.py#L168)).
Either make the card itself navigate or drop the class.

### Verify

As `cc_user` and `vc_user`: no Telemetry card, and the dashboard's own KPI links
land on reports they can read. As `staff_user`: all cards, all KPI links carry
`start`/`end` matching the dashboard's window label.

---

## T2.7 — Say what a click does

**Why.** Three reports have had a drill-down all along and communicate it with a
sentence at the bottom of the card
([`crew.py:197`](../../../pages/admin_tabs/reports/crew.py#L197): *"Click a row
to filter both tables to that person."*) or with nothing at all. Now that some
rows also carry a *navigating* control, "what does clicking do here" has to be
answerable without experimenting.

### Files

- `pages/admin_tabs/reports/crew.py`, `stream_rooms.py`, `telemetry.py`,
  `audit.py`, `shared.py`

### Change

For every table with a filtering `row-click`: the same `cursor: pointer` and the
same one-line hint, in the same place, worded the same way (`Click a row to
filter …`). `paginated_event_log` already takes a `note`
([`shared.py:328`](../../../pages/admin_tabs/reports/shared.py#L328)) — align
the others with it rather than inventing a fourth phrasing.

This is copy and CSS only. **No behaviour change**, and no new controls: if a
table needs a route out, it got one in T2.2–T2.6.

### Verify

Screenshot each of the nine reports at 1500 px and read the hints back as a set
— they should be indistinguishable in tone. That sweep is also the end-of-wave
check: **nine reports, and every row of F1's table now has a route.**
