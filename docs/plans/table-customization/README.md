# User-controlled tables — implementation plan

Give every desktop table an AWS-console-style **Preferences** gear and
drag-to-resize headers: visible columns, column order, column widths, page size,
density and line wrapping — remembered per person in Postgres, and resettable.

**Read this file completely before starting any wave.** It carries the decisions,
the ground rules and the two non-obvious mechanics that the wave files do not
repeat.

Evidence and the findings this closes: [`docs/reviews/table-ux-audit.md`](../../reviews/table-ux-audit.md).

## Wave files

| Wave | File | Theme | Migration? | Visible change |
|---|---|---|---|---|
| 1 | [wave-1-foundations.md](wave-1-foundations.md) | Model, repository, service, the request-scoped cache, the pure reconciler | **yes** | none |
| 2 | [wave-2-first-table.md](wave-2-first-table.md) | Gear + modal, end to end, on Admin → Users | no | one table customizable |
| 3 | [wave-3-widths.md](wave-3-widths.md) | Drag-to-resize, the `table-layout: fixed` CSS, width persistence | no | resizable headers |
| 4 | [wave-4-fleet.md](wave-4-fleet.md) | `table_key=` through `enable_mobile_grid` for every table; the guardrail | no | every table customizable |
| 5 | [wave-5-table-fixes.md](wave-5-table-fixes.md) | Sorting, search, pagination, sticky headers, row counts, CSV | no | the audit's other findings close |

Do not start wave N+1 until wave N is merged. Waves 1–3 are the proof; 4 is
mechanical; 5 is the audit payoff and touches the same files, which is why it is
in this plan rather than its own.

## Decisions (settled — do not relitigate)

| Question | Decision | Why |
|---|---|---|
| Storage scope | **Global per user.** `UserTablePreference(user, table_key, config)`, **no tenant FK** | `User.timezone`'s stated precedent: a person carries one answer across every community. Column identity is a property of the table, not of the community whose rows fill it. No tenant column ⇒ no leak test |
| Feature flag | **None** | Flags gate deliberately-gated subsystems with an owning service and an entry surface to hide. This is chrome on every table, including public ones |
| Audit / events | **Neither** | `AuditActions` record things done to a community's data. Hiding a column is not one. Telemetry instead (wave 2) |
| REST / MCP | **Neither** | UI state, not part of the external contract |
| Modal contents | Visible columns + reorder, page size, density, wrap lines | Widths are dragged from the header, with keyboard steppers in the modal for parity |
| Scope | Waves 1–5, i.e. customization **plus** the table findings in the same files | Splitting means touching every table twice |

## Ground rules

### 1. Desktop only — and the mobile card is protected by call order, not by a flag

Below `lt.md` every table renders as stacked cards. **The card view does not
change in this plan.** That is not achieved by an `if mobile:` anywhere; it falls
out of one ordering, which every adopting call site must follow:

```python
table = ui.table(columns=DEFAULT_COLUMNS, rows=[], row_key='id')   # 1 defaults
table.add_slot('body-cell-status', ...)                            # 2 defaults
enable_mobile_grid(table, DEFAULT_COLUMNS, ...)                    # 3 bakes the card slot from DEFAULTS
customize_table(table, DEFAULT_COLUMNS, key=...)                   # 4 rewrites table.columns
```

Step 3 renders the card's `item` slot as a **static Vue string** built from the
defaults, at build time, addressing `props.row.<field>` directly. It never reads
`table.columns` or `visible-columns`. So step 4 is invisible to it — for free,
and permanently, as long as nobody "simplifies" the order.

`test_preferences_do_not_touch_the_mobile_card` (wave 2) pins this by asserting
the generated `item` slot is byte-identical with and without a preference
applied. **If you find yourself reordering these calls, that test is the reason
not to.**

The gear button and the resize handles are *additionally* hidden below the
breakpoint — CSS on the button, `matchMedia('(min-width: 1024px)')` in the JS —
because a gear above a card list offering to reorder columns nobody can see is
worse than no gear.

### 2. Resolution is async; reading it back is sync

This is the `timezone_context.py` shape, and it exists for the same reason:
`customize_table` is called from synchronous slot-registration code, and a table
build cannot `await` a DB read per table on a page that hosts twelve of them.

- **Once per page build**, `BaseLayout.render()` awaits `TablePreferenceService().prime(user)`, which loads the user's whole preference set in **one query** and writes it into `application/table_preferences_context.py`'s contextvar.
- **Every `customize_table` call** reads it back synchronously and free.
- **Unprimed context ⇒ defaults.** A surface that doesn't use `BaseLayout` (`/platform`, the static bracket views) simply gets the shipped columns. That is a correct answer, not a failure, and nothing logs.

Two carriers must be extended, or preferences silently vanish on exactly the
surfaces that matter most:

- **`BaseLayout._build_tab`** — lazy tab content is built in a websocket handler where the contextvar is gone. It already rebinds `tenant_scope(self._tenant_id)`; add `table_prefs_scope(self._table_prefs)` beside it.
- **`admin_crud.capture_render_context()` / `scoped_background()`** — the same tuple that already carries `(tenant_id, tz)` gains the preference dict, so a background refresh repaints with the user's columns rather than the defaults.

Miss either and the bug is subtle: the table renders correctly on load and
reverts to default columns the first time you switch tabs or hit Refresh.

### 3. Defaults win for columns the user has never seen

A saved column list is a *filter over* the current defaults, never a replacement
for them. A default column absent from the saved list is **appended, visible**.
The opposite rule — honour the saved list exactly — makes every newly added
column invisible forever to everyone who has ever opened the gear, and it is a
bug you find months later from a support ticket. `effective_columns` owns this;
`test_a_new_default_column_appears_for_a_user_who_saved_earlier` pins it.

### 4. The service never learns column names

`TablePreferenceService.validate` checks **shape and bounds only** — known keys,
allowed page sizes, width range, list length, string length. It cannot validate
column *names*: the authoritative list lives in presentation, and a service
importing `theme/` inverts the architecture (`enforce_architecture.py` would
reject it). Names are reconciled in presentation by `effective_columns`, where
the defaults are. An unknown name in stored config is dropped silently at render
time — that is the mechanism for a developer deleting a column, not an error.

### 5. Everything else stays as it is

Do not change what a table *shows*, its row dicts, its slots, its handlers, its
empty state or its query in waves 1–4. Wave 5 is where behaviour changes, and it
changes one thing at a time.

## The two files everything routes through

| File | Role |
|---|---|
| `theme/tables/preferences.py` *(new — wave 1)* | `effective_columns` (pure), `customize_table`, `preferences_button`, the `table_key` constants |
| [`theme/tables/mobile_grid.py`](../../../theme/tables/mobile_grid.py) | Gains `table_key=`; the chokepoint every table already calls and `check_table_grid.py` already enforces |

**Why not a new base class.** `theme/tables/admin_crud.py`'s own docstring
records the answer: a `ServiceTableView` generic and an equipment kit were both
extracted "in anticipation of adoption that never happened", had zero importers
after two audits, and were deleted. An optional better table will not be adopted
here either. `enable_mobile_grid` is the one call every table is already
obliged to make, with a hook that fails the build when it is missing — so the
capability rides on that, and adoption stops being a choice.

## Definition of done for the whole plan

- Every desktop table in `pages/` and `theme/` either has a `table_key` or a `# table-prefs: exempt` comment, proven by a guardrail hook and a source-scanning test.
- A staff member can hide, reorder and resize columns on any board; reload, new tab and a different machine all show the same table.
- **Reset to defaults** returns the shipped configuration on every table.
- No mobile card view changed, proven by a byte-identical slot test.
- `docs/reference/frontend.md` § Responsive tables has grown into § Data tables and documents the mechanism; `docs/reference/data-model.md` carries the new model.
- `scripts/seed_dev.py` seeds preference rows so `/ui-validation` exercises the applied path.
- [`docs/reviews/table-ux-audit.md`](../../reviews/table-ux-audit.md) **and this plan directory** are deleted — the feature docs are the truth, git history holds the rationale.
