# Wave 2 — One table, end to end

The gear, the modal, the persistence and the reset — on **Admin → Users** only.

Users is the right first table: six columns, no bespoke cell slots worth
speaking of, a `UserTableView` that already owns its own toolbar, and a page
(`admin_users.py`) that renders its own controls with `show_toolbar=False` — so
the gear has an obvious home. It is also the table with **zero** sortable
columns, which makes the improvement legible to a reviewer.

At the end of this wave exactly one table is customizable, everything is
persisted, and the mechanism is proven in a browser.

---

## 1. Prime the cache once per page build — `theme/base.py`

In `BaseLayout.render()`, beside the existing `_load_theme_colors()` await:

```python
self._table_prefs = await TablePreferenceService().prime(self.user)
```

then wrap the chrome + tab render in `table_prefs_scope(self._table_prefs)`.

**Both carriers must be extended in this wave**, or the feature works on load
and silently reverts later (README, ground rule 2):

| Carrier | File | Change |
|---|---|---|
| Lazy tab build | `theme/base.py` `_build_tab` | add `table_prefs_scope(self._table_prefs)` beside the existing `tenant_scope(self._tenant_id)` |
| Background refresh | `theme/tables/admin_crud.py` | `capture_render_context()` returns `(tenant_id, tz, prefs)`; `scoped_background` rebinds all three |

`capture_render_context`'s return type is a tuple consumed in three modules
(`match.py`, `user.py`, `tournament.py`); widening it is a mechanical change but
it must be done in the same commit as the callers.

---

## 2. `customize_table` — `theme/tables/preferences.py`

```python
def customize_table(
    table: ui.table,
    defaults: Sequence[Mapping],
    *,
    key: str,
    required: AbstractSet[str] = DEFAULT_REQUIRED,
    page_size: int = 0,
    density: str = 'comfortable',
    wrap: bool = False,
) -> ColumnPlan:
    """Apply this viewer's saved preferences to ``table``'s **desktop** view.

    Call **after** ``enable_mobile_grid`` / the bespoke ``item`` slot — see the
    plan's ground rule 1. Reads the primed contextvar synchronously; an unprimed
    context yields the defaults.
    """
```

What it does, in order:

1. `plan = effective_columns(defaults, table_prefs_for(key), required)`, with the caller's `page_size`/`density`/`wrap` as the fallbacks.
2. `table.columns = plan.columns` — Quasar renders columns in array order and resolves `body-cell-<name>` slots by name, so **reordering needs nothing else**; existing slots follow their column.
3. `table._props['visible-columns'] = plan.visible` (the mechanism `apply_column_visibility` already uses; row dicts untouched, so `row_key` and every handler keep working).
4. `table.props(f'dense={plan.density == "compact"}')`, `pagination` set from `plan.page_size` (`0` ⇒ omit the prop, which is today's behaviour).
5. Toggle `wiz-table--wrap` / `wiz-table--sized` classes.
6. `table.update()`; return the plan.

It also **registers the two client events once per table** (`wiz_table_width`
lands in wave 3; wave 2 only needs the modal's save path) and stashes
`(key, defaults, required)` on the table object so the gear's dialog can be
built from one argument.

## 3. The gear — `preferences_button(table, plan, *, key, defaults, required)`

`ui.button(icon='settings')` with `.props('flat round dense')`, tooltip
*"Table preferences"*, `.classes('wiz-table-prefs-btn')`. Two details:

- A small dot badge when `plan.is_customized`, so "why does my table look like this" has an answer on screen.
- `.classes(REQUIRES_SOCKET_CLASS)` — saving is a round trip, so it obeys the [offline honesty](../../reference/frontend.md#offline-honesty-themeconnectionpy) rules like every other writing control.

CSS hides it below `1024px` (`static/css/styles.css`, beside the existing
`.wiz-filter-toggle` rules).

## 4. The modal — `theme/dialog/table_preferences_dialog.py` (new)

Built on `form_dialog('Table preferences')` so it inherits the mobile sheet,
header and sticky action bar. **Staged, not live**: edits mutate a local copy;
Cancel discards.

| Section | Control | Notes |
|---|---|---|
| Page size | `ui.radio({0: 'All', 10: '10', 25: '25', 50: '50', 100: '100'})` | `All` first — it is today's behaviour and must stay reachable |
| Density | `ui.radio(['Comfortable', 'Compact'])` | |
| Wrap lines | `ui.switch('Wrap long values')` | Off ⇒ ellipsis + `title` tooltip |
| Columns | one row per column: `ui.checkbox` · label · ▲ · ▼ · width `ui.number` | Required columns render a **disabled** checkbox with a "Always shown" caption — disabled, not missing, so the absence is explained |

Footer: **Reset to defaults** (left, `flat`) · spacer · **Cancel** · **Confirm**
(`color=primary`).

- **Confirm** → `await TablePreferenceService().save(user, key, staged)`, catch `ValueError` → `ui.notify(str(e), color='warning')`, then re-apply to the live table via `customize_table` and `ui.notify('Preferences saved')`. No page reload.
- **Reset** → `await service.reset(user, key)`, re-apply defaults, close. It resets *this* table only; a global reset is not offered (nobody asks for it, and it is one line in a support script).

Keyboard: the ▲/▼ buttons and the width `ui.number` are the accessible
equivalents of drag-to-reorder and drag-to-resize. Drag-to-reorder is a wave-4
enhancement layered on top, never a replacement.

## 5. Wire Admin → Users

`theme/tables/user.py` — `UserTableView.__init__` gains `table_key: Optional[str] = None`;
when set, after `render_grid_slot()` and the `extra_slots` loop:

```python
self._plan = customize_table(self.table, self.columns, key=self.table_key)
```

Note the position: **after** the `item` slot is generated (ground rule 1). Add a
short comment saying so, pointing at the test.

`pages/admin_tabs/admin_users.py` passes `table_key=TableKeys.ADMIN_USERS` and
renders `preferences_button(...)` in its existing button row, between **Add
User** and the refresh button.

`refresh()` must reapply the plan after it repaints — it assigns `self.table.rows`
only, so `columns` survive; assert this rather than assume it, because a future
`refresh` that rebuilt columns would silently drop preferences.

## 6. Telemetry

`save` and `reset` already fire `track_interaction` (wave 1). Nothing to do here
beyond confirming the events land in **Admin → Reports → Engagement**, which is
how adoption gets measured without a new report.

---

## 7. Tests

`tests/theme/test_table_preferences.py`:

| Test | Pins |
|---|---|
| `test_preferences_do_not_touch_the_mobile_card` | **The ground-rule-1 guarantee.** Build a table, capture the `item` slot; apply a plan that hides and reorders columns; assert the `item` slot string is byte-identical |
| `test_visible_columns_prop_matches_the_plan` | step 3 |
| `test_column_order_follows_the_saved_order` | step 2 |
| `test_row_dicts_are_untouched_by_hiding` | `row_key` and handlers survive |
| `test_an_unprimed_context_renders_defaults` | `/platform` and the public pages |
| `test_capture_render_context_carries_preferences` | the wave's subtlest bug: a background refresh reverting to defaults |
| `test_required_columns_render_a_disabled_checkbox` | the modal explains the absence |

`tests/theme/test_admin_toolbar_wiring.py` — extend the existing source scan with
`test_customize_table_is_called_after_the_grid_slot`: for every file calling both
`enable_mobile_grid` and `customize_table`, assert the AST order. A comment is not
enforcement; this is.

## 8. Browser pass — `/ui-validation`

Not optional. The Vue slot behaviour in ground rule 1 is only observable in a
real browser; the SQLite suite and `nicegui.testing` cannot see it.

1. Sign in as staff, open **Admin → Users**.
2. Gear → hide **Pronouns**, move **Roles** above **Challonge**, page size 25, Compact → Confirm.
3. Screenshot. Reload. Screenshot — identical.
4. Open a second browser profile as the same user; confirm the same layout (proves it is not session storage).
5. Resize the viewport to 390px: cards render exactly as on `main`, and **no gear is visible**. Screenshot both for the PR.
6. Gear → **Reset to defaults**. Confirm the shipped six columns return.

---

## Acceptance

- Admin → Users is customizable; every other table is untouched (`git grep -n table_key` shows one call site).
- All new tests green; `tests/theme/test_admin_toolbar_wiring.py` still green.
- The six screenshots are in the PR, including the two mobile ones.
- `python3 scripts/guardrails.py` clean.
