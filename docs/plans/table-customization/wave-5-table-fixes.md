# Wave 5 — The rest of the audit

The customization mechanism is done. This wave closes the findings that live in
the same files, one at a time, then retires the audit and this plan.

Each section below is independently revertable. Land them as separate commits in
one PR so a reviewer can read them apart.

---

## 1. Sorting on the boards that lack it — finding F1

Add `'sortable': True` to the columns where a sort is meaningful. Not all of
them: a sort is meaningful on a scalar, and misleading on a rendered
comma-joined list where the sort would run on the string.

| Board | Add `sortable` to | Leave alone |
|---|---|---|
| Admin → Users (0/6) | `username`, `preferred_name`, `pronouns`, `challonge` | `roles` (joined string), `actions` |
| Admin → Tournaments (0/10) | `name`, `seed_generator`, `is_active`, `players_per_match`, `average_match_duration`, `max_match_duration`, `staff_administered`, `player_count` | `description` |
| Home → Player (0/7) | `tournament`, `scheduled_at`, `state`, `stream_room` | `players`, `generated_seed`, `watch` |
| Admin → Qualifiers (0/8, 0/5) | the name/date/status scalars | rendered action cells |
| Player qualifiers (0/6, 0/5) | `rank`, time, status | |
| Admin → Schedule (4/9) | `generated_seed` (present/absent sorts usefully) | `players`, `commentators`, `trackers`, `edit` |

**Check what each column actually holds before declaring it sortable.** Quasar
sorts the raw field value, so a formatted string sorts as text.

Two things were verified while writing this plan, and the answers are not
symmetric:

- **Date columns are safe.** Every one goes through `format_local_datetime` (`%Y-%m-%d %H:%M`) or `format_local_display` (the same, plus a zone label), and an ISO-ordered zero-padded prefix sorts lexically exactly as it sorts chronologically. `scheduled_at` needs no `:sort` and no numeric twin. (An earlier draft of this plan claimed otherwise; it was wrong.)
- **Formatted numbers were not.** The Tournament-health table declared four such columns sortable — three percentages rendered `'85%'` and a score falling back to `'—'` — so `'100%' < '10%' < '9%'` and the report ranked backwards. **Fixed ahead of this wave** (`health_display_rows` in `reports/insights.py`, with `TestHealthDisplayRows` pinning it): the number stays in the field Quasar sorts, the rendering rides beside it in `<name>_display`, and one snippet per field serves the desktop cell and the mobile card.

Note that NiceGUI 3.12 passes column dicts to Quasar as **plain JSON** — there is
no `:sort` or `:format` function support — so the number-beside-its-rendering
shape above is the only fix available, and it is the pattern to copy for any new
sortable formatted column.

Everything else in the reports was swept and is clean: the aggregates carry raw
numbers, `_ratio_pct` returns a float, and the composite cells (`'6/8'`,
`'41 (40)'`, `'2/3 · need 2'`) are deliberately not sortable.

## 2. Real text search — finding F3

Delete the twelve dead `'filterable': True` declarations and the one
`'clickable': True`, and implement what they were reaching for.

`enable_mobile_grid` / `customize_table` gain `searchable: bool = False`. When
set, render a `ui.input(placeholder='Search…')` with a `search` icon in the
table's toolbar and bind it to Quasar's real `filter` prop
(`table.bind_filter_from(search_input, 'value')`). Quasar filters across all
visible columns by default; a `filter-method` is only needed if a table wants to
restrict it.

Turn it on for the boards where "find one row" is the actual task: Admin → Users,
Admin → Tournaments, Admin → Schedule, Proctor Station, the equipment
inventories, `/platform` tenants. Not the reports — they filter server-side by
design, and a second client filter over one page of results is a trap.

Search text is **not** persisted. It is a working state, not a preference.

## 3. Pagination on the three unbounded boards — finding F2

Uncomment and set a real default in `theme/tables/{match,user,tournament}.py`:
`pagination={'rowsPerPage': 25, 'page': 1}` — overridden per person by the
preference from wave 2.

Then fix the wiring that comes with it. All three currently do:

```python
self.table.on('update:pagination', self._on_page_change)   # → full server refresh
```

With pagination live, that re-queries the database on every page turn of data the
client already holds. **Delete it.** Quasar paginates client-side over
`table.rows`; the server has nothing to do. Keep the explicit Refresh button,
which is what the handler was really covering for.

Check each `_on_page_change` for a second responsibility before deleting — the
match view's is also its initial-load trigger in one path, and that path must
keep working (`_bg(self._initial_load())` already covers it; verify).

Row counts: add the `_page_range_label` treatment from
`reports/shared.py` — *"Showing 51–100 of 124 users"* — above each paginated
table. It is already written, already good, and lifting it is a rename away.

## 4. Sticky headers — finding F8

`table.props('virtual-scroll-sticky-size-start=48')` plus the Quasar sticky
header CSS on `.wiz-table` and the four family classes. Guard it on
`max-height` being set — a sticky header on an unconstrained table does nothing
and costs a repaint. Apply to the boards, not to short reference tables.

## 5. CSV on the operational boards — finding F8

`csv_export_button(prefix, columns_provider, rows_provider)` already exists in
`reports/shared.py` and is generic. Move it to
`theme/tables/export.py` (a presentation peer, not a report detail), re-export
from `reports/shared.py` so the reports keep importing it, and add it to Admin →
Users, Admin → Schedule and Admin → Tournaments.

Export **what the user sees**: the visible columns in their order, i.e. the
`ColumnPlan`, not the defaults. That falls out of passing
`lambda: view._plan.columns` as the provider, and it is the reason this is in
wave 5 rather than earlier.

## 6. Decompose the event-log body slot — finding F7

`reports/shared.py:510` `paginated_event_log` registers a whole-`body` slot with
hardcoded `<q-td>`s, so column order and visibility have no effect. Split
`_EVENT_LOG_DETAILS_CELL` into per-column `body-cell-*` slots, keep the row-click
wrapper as a `body` slot that renders `<q-td v-for>` over `props.cols` (Quasar's
own idiom), then remove the `table-prefs: exempt` from wave 4 and give the Audit
Log and Telemetry tables their keys.

If the row-click wrapper cannot be preserved cleanly, leave the exemption in
place with the reason updated — two report tables without column customization is
an acceptable outcome; a broken drill-down is not.

## 7. Docs, seed, and retirement

- **`docs/reference/frontend.md`** — grow *§ Responsive tables — the mobile grid rule* into *§ Data tables*, covering: the two guardrails, `enable_mobile_grid`'s new `table_key`, the call-order rule and why it is what protects the mobile card, the prime/read-back split, and the reconciliation rules. Keep it a table of names and one-line purposes, per the docs conventions; the wave files hold the rationale until they are deleted.
- **`docs/reference/data-model.md`** — already updated in wave 1; verify it survived.
- **`CLAUDE.md`** — one line under NiceGUI patterns: every `ui.table` needs a mobile card **and** a `table_key`. The rule belongs there; the mechanism does not.
- **`scripts/seed_dev.py`** — verify the wave-4 rows still seed after the wave-5 column changes.
- **Delete** `docs/reviews/table-ux-audit.md`, its row in `docs/reviews/README.md`, and this whole `docs/plans/table-customization/` directory — adding the audit to the "Shipped and deleted" paragraph in the reviews README with a one-line summary of what its findings became. That paragraph is the institutional memory; the files are not.

---

## Tests

| Test | Pins |
|---|---|
| `test_no_column_declares_filterable_or_clickable` | source scan — the dead conventions do not come back |
| `test_sortable_columns_sort_on_a_sortable_value` | every `sortable` column's field is a scalar or carries an explicit `:sort` |
| `test_the_family_views_do_not_refresh_on_pagination` | source scan for `on('update:pagination'` in the three views |
| `test_csv_export_follows_the_visible_plan` | §5 — exports what is seen |
| `test_page_range_label_reads_correctly_at_the_boundaries` | already exists for reports; extend to the boards |

Plus a `/ui-validation` pass on Admin → Users and Admin → Schedule: sort each
newly-sortable column and confirm the order is correct (especially the date
columns from §1), search for a row, page through, export the CSV and diff its
header against the visible columns.

---

## Acceptance

- Every finding in [the audit](../../reviews/table-ux-audit.md) is either closed or explicitly recorded as declined with a reason.
- `docs/reviews/table-ux-audit.md` and `docs/plans/table-customization/` no longer exist; the reviews README's "Shipped and deleted" paragraph names what they became.
- Full suite green; `python3 scripts/guardrails.py` clean.
