# Table UX audit — and a plan for user-controlled tables

_Point-in-time audit of every `ui.table` in the app, plus the implementation plan
for AWS-console-style table customization: visible columns, column order, column
widths, page size — remembered per user, and resettable. Transient by the
[docs conventions](../README.md#conventions-for-this-directory): delete once the
work ships._

**Scope note.** Customization is a **desktop-table** concern only. Below Quasar's
`lt.md` breakpoint every table renders as stacked cards
([the mobile grid rule](../reference/frontend.md#responsive-tables--the-mobile-grid-rule)),
and the card view stays exactly as it is today — no gear, no resize handles, no
reordering. A phone card has one column; there is nothing to customize, and the
card's field order is a designed reading order, not a default someone should be
able to scramble. Everything below applies at ≥1024px unless it says otherwise.

---

## 1. What is actually there

41 column lists across 32 `ui.table` call sites in `pages/` and `theme/`
(snapshot; the numbers are the measurement, not a maintained count). They fall
into five construction styles that share almost nothing:

| Style | Where | Toolbar | Empty state | Mobile card |
|---|---|---|---|---|
| **Family view — match** | [`theme/tables/match.py`](../../theme/tables/match.py) (admin Schedule, Proctor Station, home Schedule, home Player) | bespoke filter card + 3 refresh buttons | `no_data_slot` | bespoke ([`match_grid.py`](../../theme/tables/match_grid.py)) |
| **Family view — user** | [`theme/tables/user.py`](../../theme/tables/user.py) | Add + refresh, suppressible | `no_data_slot('group')` | bespoke, column-driven |
| **Family view — tournament** | [`theme/tables/tournament.py`](../../theme/tables/tournament.py) | Add + refresh | `no_data_slot` | bespoke, hand-written per field |
| **Generic helper** | `enable_mobile_grid(...)` — ~20 admin/report tables | whatever the tab hand-rolls | usually none | generated from `columns` |
| **Hand-rolled** | `/platform` (3), Service Health, both Equipment surfaces, Stream Rooms, mock login | ad hoc | none | inline `:grid` + bespoke `item` |

`theme/tables/admin_crud.py` records what happened the last two times someone
tried to unify this: a `ServiceTableView` generic and an equipment kit were both
extracted "in anticipation of adoption that never happened", found zero
importers after two audits, and were deleted. **That is the most important
constraint on this plan** — see §4.

### What every table already does

Sorting is Quasar's, per column, opt-in via `{'sortable': True}`. Mobile cards
are mandatory and guardrail-enforced (`check_table_grid.py`). `{'hidden': True}`
is translated into Quasar's real `visible-columns` prop by
`apply_column_visibility`. Row dicts are never trimmed, so hiding a column never
breaks the handler that keys on it.

### What no table does

No column visibility control. No column reordering. No column resizing. No page
size control. No density or wrap control. No sticky header. No text search. No
row selection or bulk actions. No CSV export outside the Reports tab. And, with
one partial exception, **no memory of anything**.

---

## 2. Findings

### F1 — The boards people live in are the least capable ones

99 of 228 declared columns are sortable, and they are not evenly spread. Every
Reports table is fully or nearly fully sortable (`match_ops` detail 9/9, agg 8/8,
`crew` contributions 8/8, `stream_rooms` 5/5 and 5/5, `telemetry` 6/6). The
operational boards are not:

| Board | Columns | Sortable |
|---|---|---|
| Admin → Users ([`admin_users.py:95`](../../pages/admin_tabs/admin_users.py)) | 6 | **0** |
| Admin → Tournaments ([`admin_settings.py:33`](../../pages/admin_tabs/admin_settings.py)) | 10 | **0** |
| Home → Player, "Your Schedule" ([`player.py:181`](../../pages/home_tabs/player.py)) | 7 | **0** |
| Admin → Qualifiers, both tables ([`admin_qualifiers.py:575,638`](../../pages/admin_tabs/admin_qualifiers.py)) | 8, 5 | **0**, **0** |
| Player qualifier runs / leaderboard ([`qualifiers.py:314,388`](../../pages/qualifiers.py)) | 6, 5 | **0**, **0** |
| Admin → Schedule ([`admin_schedule.py:62`](../../pages/admin_tabs/admin_schedule.py)) | 9 | 4 |
| Home → Schedule ([`schedule.py:25`](../../pages/home_tabs/schedule.py)) | 8 | 4 |

A staff member cannot sort the user list by anything, including the Roles column
they came to the page to read. The inverse of what you would choose: a report is
read once and re-run with different filters, a board is worked all day.

### F2 — Pagination is disabled on exactly the three tables that grow without bound

All three family views construct their table with the pagination argument
commented out — [`match.py:373`](../../theme/tables/match.py),
[`user.py:49`](../../theme/tables/user.py),
[`tournament.py:45`](../../theme/tables/tournament.py) — so the whole result set
renders as one DOM table. Every community's entire user list, every match the
filters admit, in one `<tbody>`.

Worse, all three then wire `table.on('update:pagination', self._on_page_change)`
to a **full server-side reload**. With pagination off that event is Quasar
incidentally firing once at mount; with pagination on it would re-query the
database on every page turn of data the client already holds.

Report tables do paginate, at 25 or 15 rows depending on which file you are in
(`capacity` 25, `crew` 25, `insights` 15, `match_ops` 25, `volunteers` 25,
`stream_rooms` 25). Nobody can change any of them.

### F3 — Two invented column properties that nothing honours

`{'filterable': True}` appears on 12 columns across
[`schedule.py`](../../pages/home_tabs/schedule.py),
[`admin_schedule.py`](../../pages/admin_tabs/admin_schedule.py) and
[`proctor_station.py`](../../pages/volunteer_tabs/proctor_station.py).
`{'clickable': True}` appears once
([`admin_schedule.py:81`](../../pages/admin_tabs/admin_schedule.py)). Neither is
a Quasar column property, and nothing in this codebase reads either one. No
table sets Quasar's actual `filter` prop, so there is no text filtering anywhere
for them to feed.

This is the same bug class the `hidden` convention had before
`apply_column_visibility` — the frontend doc already draws the lesson: *when you
invent a flag a third-party component is also expected to honour, prove the
third party honours it.* Here it recurred twice more, and this time the flags
are not half-working, they are inert. Whoever wrote `filterable` was describing
an intent — "this column is worth searching" — that the plan below should
finally cash in.

### F4 — Column widths are three unrelated accidents

Widths come from (a) content, via `table-layout: auto`; (b) two global CSS caps
on an inner `.wrap` span — 320px for user/tournament cells, **120px for every
match cell** ([`styles.css:1425-1445`](../../static/css/styles.css)); and (c)
nothing else. The 120px cap is a single guess applied to the Players,
Commentators and Trackers columns of the busiest board in the app, and it is why
a three-name commentator list stacks into three lines on a 2560px monitor. No
user can widen it; no developer can either, without changing it for everybody.

### F5 — The one thing that is remembered is remembered in the wrong place

The match board persists its Day / Tournament / Stage / State filters through
`tenant_session_get` / `tenant_session_set`
([`application/utils/tenant_session.py`](../../application/utils/tenant_session.py)),
which namespaces `app.storage.user` per tenant. Good design, wrong substrate for
anything we want to keep: NiceGUI persists `app.storage.user` to `.nicegui/` in
the working directory, `docker-compose.yml` mounts a volume for Postgres and
**none for the app**, so the store dies with the container on every deploy. It
also does not follow the user to a second browser or a phone.

For a filter that is arguably right — a filter is a working state, and starting
fresh after a deploy is defensible. For "these are my columns", it is not.

### F6 — Five ways to build a table means five of everything

Empty states: `no_data_slot` with a tuned message on the family tables, nothing
at all on most generic tables (Quasar's default "No data available" in a
different typeface). Toolbars: Add+refresh, refresh only, bespoke filter card, or
nothing. Row actions: `_ROW_ACTIONS` constants shared between desktop cell and
mobile card in the good cases; duplicated in the others. Density: `flat dense`
on the webhook reference table and nowhere else. This is the substrate the plan
has to attach to, and it argues strongly for attaching to the *one* call every
table already makes rather than to a new base class (§4).

### F7 — Two report tables cannot support column customization as written

[`reports/shared.py:510`](../../pages/admin_tabs/reports/shared.py)
(`paginated_event_log`, used by the Audit Log and Engagement Telemetry reports)
registers a whole-`body` slot with hardcoded `<q-td>`s rather than per-column
`body-cell-*` slots. Reordering or hiding a column in the column list would have
no effect on what that slot paints. These two need the slot decomposed before
they can join, or a documented exemption.

### F8 — Smaller things worth folding into the same pass

- **No sticky header.** Scroll a 200-row board and you are reading unlabelled columns.
- **No row count.** No table says how many rows it is showing, except the two paginated event logs, which say it well (`Showing 51–100 of 124 entries`) — a pattern worth lifting.
- **CSV export exists only on Reports** (`csv_export_button`), not on the operational boards where "send me the list" is a real request.
- **No row selection, no bulk actions** anywhere. Out of scope for this plan, but it is the other half of what "AWS-console table" means to most people; noted so the mechanism below does not foreclose it.

---

## 3. The target pattern

The AWS console's table pattern (Cloudscape `Table` + `CollectionPreferences`) is
worth copying because it settles the same questions this app keeps answering
differently:

- One **gear** in the table header opens one modal. Everything customizable lives there; nothing customizable lives outside it.
- The modal carries **page size** (radio), **wrap lines** and **density** (toggles), and a **column list** with per-column visibility checkboxes and reordering.
- **Widths are not in the modal.** They are set by dragging the divider between two headers, and they persist like everything else.
- The modal footer is **Cancel / Confirm** — changes are staged, not live — plus a **Reset to defaults** that returns the table to the shipped configuration.
- Preferences are **per user, per table**, and survive a reload, a new tab, and a different machine. The app owns storage; the component owns nothing.
- Required columns cannot be hidden, and a column the user has never seen (because a developer added it after they saved) **appears** rather than staying invisible forever.

Adapted to this app: keep the shipped column order and visibility as the
defaults, keep sorting where it already is (Quasar's header click), add the gear
and the resize handles, and store the result in Postgres.

---

## 4. Design

### 4.1 The load-bearing decision: hang it on the call that already exists

The two previous unification attempts died because they were *optional* — a
better base class nobody had to adopt. There is exactly one thing every table in
this app is already obliged to do, and a guardrail hook that fails the build when
it doesn't: `enable_mobile_grid(table, columns, ...)`, or for the four family
views, `apply_column_visibility(table, columns)`.

So: **`table_key` becomes a parameter of `enable_mobile_grid`**, and
`check_table_grid.py` grows a second assertion requiring one (with the same
`# table-prefs: exempt` escape hatch as the existing `# mobile-grid: exempt`).
Adoption is then not a choice; it is the same one-line call every table already
makes, with one more argument. The family views call the new
`customize_table(...)` directly, as they already call `apply_column_visibility`
directly.

No new base class. No `ServiceTableView` III.

### 4.2 Order of operations — this is what keeps mobile untouched

The single most important implementation constraint, and the easiest to get
wrong:

```
1. build ui.table(columns=DEFAULT_COLUMNS)      # defaults
2. register body-cell-* slots                   # defaults
3. enable_mobile_grid(table, DEFAULT_COLUMNS)   # bakes the `item` card slot from DEFAULTS
4. customize_table(table, DEFAULT_COLUMNS, key) # rewrites table.columns + visible-columns
```

Step 3 generates the mobile card's `item` slot as a **static Vue string** from
the defaults, at build time. Step 4 mutates `table.columns` and the
`visible-columns` prop, which the card slot does not read — it addresses
`props.row.<field>` directly. So the card is structurally immune to every
preference, for free, which is exactly the desired behaviour. The plan must
**not** "simplify" by applying preferences before the card is generated, and a
test should pin this (§6).

The resize handles and the gear button are additionally hidden below the
breakpoint in CSS and short-circuited in JS on `matchMedia('(min-width: 1024px)')`
— belt and braces, because the gear would otherwise sit above a card list
offering to reorder columns that aren't rendered.

### 4.3 Storage

**Model** — `UserTablePreference` in a new `models/preferences.py`, re-exported
from `models/__init__.py`:

| Field | Type | Note |
|---|---|---|
| `user` | FK → `User`, `CASCADE` | |
| `table_key` | `CharField(64)` | e.g. `admin.users`, `report.match_ops.detail` |
| `config` | `JSONField` | the whole preference blob |
| `updated_at` | `DatetimeField(auto_now=True)` | |

`unique_together = ('user', 'table_key')`.

**No `tenant` FK — deliberately.** This is the `User.timezone` case, whose model
comment already states the reasoning: *a person carries one timezone across every
community they belong to.* The same is true of "I never use the Pronouns column".
Column identity is a property of the table, not of the community whose rows fill
it, and a staff member in two communities wants one answer, not two. The
practical consequence is welcome: with no tenant column there is no tenant leak
to test for. **This is the one decision worth a second opinion before Wave 0
lands** — the alternative (tenant-scoped, `_tenant.py`-scoped repo, leak test)
is a day's work now and a migration later.

**`config` shape**, validated by the service and otherwise opaque to it:

```json
{
  "columns": [{"name": "username", "visible": true, "width": 220}, ...],
  "page_size": 25,
  "density": "comfortable",
  "wrap": false
}
```

The service validates *shape and bounds* — known top-level keys, `page_size` in
an allowed set, `width` an int within 40–1200, `columns` a list of ≤64 objects,
`name` a ≤64-char string — and never validates column *names*. It cannot: the
authoritative column list lives in the presentation layer, and a service reaching
into `theme/` would invert the architecture. Reconciliation against the real
columns happens in presentation, where the defaults are.

### 4.4 Reconciliation — the rule that decides whether this ages well

One pure function, unit-tested, no NiceGUI import:

```python
def effective_columns(defaults: list[dict], saved: dict | None,
                      required: set[str]) -> tuple[list[dict], list[str]]
```

- A saved column **not** in `defaults` is dropped (a developer removed it).
- A default column **not** in `saved` is **appended, visible** (a developer added it after this user last saved). The opposite rule — respect the saved list exactly — makes every new column invisible forever to everyone who ever opened the gear, and it is a bug you find months later.
- A `required` column (`actions`, `edit`) is forced visible regardless of what is saved; the modal renders its checkbox disabled with a reason, not missing.
- If every column would end up hidden, fall back to defaults rather than paint an empty table.
- Widths are applied as `style`/`headerStyle` on the column dict, and only take effect alongside `table-layout: fixed`, which the CSS applies only when at least one width is set — an unresized table keeps today's content-driven layout exactly.

### 4.5 Reading preferences without N queries

A page can host a dozen tables (Reports, `/platform`). Mirror
`FeatureFlagService.enabled_flags()`: one `all_for_user(user)` call per request,
cached in a contextvar, returning `dict[table_key, config]`. Tables read from the
cache synchronously during their build; a save invalidates it.

### 4.6 Column resizing

Quasar's `QTable` has no built-in column resizing, so this is ours:
`static/js/table-columns.js`, loaded once from `BaseLayout.render_chrome()`
alongside the connection watcher.

- **One delegated `pointerdown` listener on `document`**, not injected handle elements. Hit-test the last ~6px of a `th` inside a `.wiz-table`/family table. Injected nodes would be destroyed on every Vue re-render — and these tables re-render on every row refresh, of which the match board has many.
- Drag updates the `<col>`/`th` width live; `pointerup` emits one `wiz_table_width` event to the server (`emitEvent`), which persists it. No round trip during the drag.
- **Double-click a divider = auto-fit** that column (clears its stored width), matching the console.
- Guarded on `matchMedia('(min-width: 1024px)')` and on `document.body.classList.contains('wiz-offline')` — a resize is a round trip, so it belongs to the [offline honesty](../reference/frontend.md#offline-honesty-themeconnectionpy) rules like everything else that writes.
- Keyboard path: the preferences modal is the accessible equivalent — width steppers per column, so resizing is not mouse-only. (Cloudscape does the same thing for the same reason.)

### 4.7 The preferences modal

`theme/dialog/table_preferences_dialog.py`, built on the existing `form_dialog`
chrome so it inherits the sticky action bar:

- **Page size** — radio: 10 / 25 / 50 / 100 / All. "All" is what today's family tables do, so it must remain reachable.
- **Density** — Comfortable / Compact (`dense` prop).
- **Wrap lines** — off wraps nothing (ellipsis + title attribute); on releases the `.wrap` max-widths from F4.
- **Columns** — one row per column: checkbox, label, ▲/▼ reorder buttons, and a width stepper. Drag-to-reorder is a Wave-4 enhancement; the buttons ship first because they are keyboard- and touch-workable and cost nothing.
- Footer: **Reset to defaults** (left) · **Cancel** · **Confirm** (right). Staged, not live — Cancel means cancel.

### 4.8 What this feature deliberately does not get

- **No feature flag.** [CLAUDE.md](../../CLAUDE.md#feature-flags) requires the question be asked; the answer here should be no. Flags are for deliberately-gated subsystems with an owning service and an entry surface to hide. This is page chrome on every table in the app, including public ones — gating it would mean a flag check in the hottest UI path for a capability nobody would ever turn off. **Confirm before Wave 0.**
- **No audit row, no domain event.** `AuditActions` are `verb.object` records of things done to the community's data. "someone hid the Pronouns column" is not one. Recommend instead a `TelemetryService` interaction on save/reset, so adoption is measurable in the existing Engagement report.
- **No REST or MCP surface.** Preferences are UI state, not part of the external contract.

---

## 5. Rollout

Each wave is independently shippable and independently revertable.

| Wave | Content | Visible change |
|---|---|---|
| **0 — Foundations** | `UserTablePreference` + aerich migration; `table_preference_repository.py`; `TablePreferenceService` (get / all_for_user / save / reset, shape validation, per-request cache); `theme/tables/preferences.py` with `effective_columns` + the `table_key` registry; unit tests | none |
| **1 — One table, end to end** | Gear + modal on **Admin → Users** (6 columns, no bespoke slots, lowest risk): visibility, order, page size, density, wrap, persistence, reset | Users table becomes customizable |
| **2 — Widths** | `static/js/table-columns.js`, the `table-layout: fixed` CSS, the `wiz_table_width` handler, width steppers in the modal; adopt on Users, then Admin → Schedule | drag-to-resize on two boards |
| **3 — Fleet** | `table_key=` threaded through `enable_mobile_grid` for the ~20 generic tables; the four family views wired directly; `check_table_grid.py` gains the second assertion; `# table-prefs: exempt` on the genuinely-static ones (webhook header reference, mock login picker) | every table customizable |
| **4 — The rest of "modern"** | Sticky headers; Quasar's real `filter` prop wired to a search box, finally cashing in the dead `filterable` flags (F3) and deleting `clickable`; a row-count line modelled on `_page_range_label`; pagination restored on the three unbounded boards (F2) with the `update:pagination` full-reload wiring fixed; sortable added to the boards that lack it (F1); CSV export on the operational boards | the table stops being the weakest part of the page |
| **5 — Close out** | `reports/shared.py`'s whole-`body` slot decomposed into `body-cell-*` (F7) or exempted; `frontend.md` § Responsive tables extended into § Data tables; `seed_dev.py` seeds a couple of preference rows so `/ui-validation` exercises the applied path; **this file deleted** | — |

Waves 0–2 are the proof; 3 is mechanical; 4 is where the audit's other findings
get paid off. If only part of this ships, ship 0–3.

---

## 6. Tests

- **`effective_columns` unit tests** — new column appears, removed column drops, required column can't be hidden, all-hidden falls back, widths clamp, ordering respected. Pure function, no NiceGUI, cheap.
- **Service tests** — shape validation rejects unknown keys / out-of-range widths / oversized lists; save is upsert-idempotent; reset deletes; `all_for_user` is one query.
- **`tests/theme/test_table_preferences_desktop_only.py`** — the constraint from §4.2, pinned: build a table, apply a preference that hides and reorders columns, assert the `item` slot template is byte-identical to the one built from defaults. This is the test that keeps the mobile card safe when someone later refactors the call order.
- **Guardrail test** — every presentation `ui.table` has a `table_key` or an exemption comment (mirrors the existing `test_admin_toolbar_wiring.py` shape).
- **`/ui-validation` browser pass** — hide a column, reorder, resize, reload, confirm it held; reset, confirm defaults; then at 390px confirm the cards are unchanged and no gear is rendered. The Vue slot behaviour in §4.2 is only observable in a real browser, which is what that skill exists for.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Preferences applied before the card slot is generated → mobile cards inherit desktop customization | Documented order in §4.2, pinned by a theme test |
| Resize handles destroyed by Vue re-render on refresh | Delegated document listener + CSS pseudo-elements; no injected DOM |
| A developer adds a column; existing users never see it | The append-visible reconciliation rule (§4.4), unit-tested |
| Width persistence chattiness on the match board (frequent refreshes) | One write on `pointerup` only; never during drag |
| `table_key` collisions across pages | Central registry in `theme/tables/preferences.py`; guardrail asserts uniqueness |
| Tenant-scoping decision reversed later | Cheap now, a data migration later — hence the open question below |

---

## 8. Decisions

Settled with the maintainer; the execution plan is
[`docs/plans/table-customization/`](../plans/table-customization/README.md).

| Question | Decision |
|---|---|
| Preference scope | **Global per user** — no tenant FK, per §4.3 |
| Feature flag | **None**, per §4.8 |
| Build scope | **Customization plus the table findings it touches** — sorting, search, pagination and sticky headers ship in the same waves rather than a separate PR, because they live in the same files |
| Modal contents | Visible columns + reorder, page size, density, wrap lines |

**Row selection and bulk actions remain out of scope** — the other half of the
console table pattern, deliberately excluded. The mechanism does not foreclose
it; it is worth its own decision.
