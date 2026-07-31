# Wave 4 — Every table

Thread `table_key` through the chokepoint, wire the remaining ~30 tables, and add
the guardrail that stops a new table shipping without one.

Mechanical by design: the mechanism was proven in waves 2–3, so this wave should
be reviewable as a large diff of small identical changes.

---

## 1. The chokepoint — `theme/tables/mobile_grid.py`

```python
def enable_mobile_grid(
    table, columns, *, actions='', field_slots=None, row_click_event=None,
    breakpoint=MOBILE_GRID_BREAKPOINT,
    table_key: Optional[str] = None,        # NEW
    required: Optional[AbstractSet[str]] = None,
    page_size: int = 0, density: str = 'comfortable', wrap: bool = False,
) -> ui.table:
```

The card slot is generated from `columns` **first**, exactly as today; then, if
`table_key` is given, `customize_table(...)` is called as the last statement.
That ordering is the ground-rule-1 guarantee made structural: a caller who goes
through `enable_mobile_grid` **cannot** get it wrong, because the helper owns
both calls. Say so in the docstring.

`theme/tables/mobile_grid.py` imports `theme/tables/preferences.py` — a
presentation → presentation import, fine.

## 2. Adoption sweep

One call site at a time; each is one added kwarg. Keys go in `TableKeys` in
`theme/tables/preferences.py`, namespaced `surface.table`.

**Family views** (`table_key` param on the class, `customize_table` after the
bespoke `item` slot — these do **not** route through `enable_mobile_grid`):

| Surface | Key | File |
|---|---|---|
| Admin → Users | `admin.users` | wave 2, done |
| Admin → Schedule | `admin.schedule` | wave 3, done |
| Proctor Station | `volunteer.proctor_station` | `pages/volunteer_tabs/proctor_station.py` |
| Home → Schedule | `home.schedule` | `pages/home_tabs/schedule.py` |
| Home → Player | `home.player_matches` | `pages/home_tabs/player.py` |
| Admin → Tournaments | `admin.tournaments` | `theme/tables/tournament.py` + `admin_settings.py` |
| Equipment (3 surfaces) | `equipment.inventory`, `equipment.mine`, `admin.equipment` | inline tables, wire `customize_table` directly after their `item` slots |

Four `MatchTableView` surfaces, four keys — the proctor's board and the admin
board are different tables that happen to share a class, and a proctor's column
choices must not follow them onto the admin board.

**Generic tables** (`enable_mobile_grid(..., table_key=…)`): admin_racetime,
admin_speedgaming, admin_brackets/page, admin_presets, admin_discord_events (×2),
admin_discord_roles, admin_webhooks (list + deliveries), admin_feedback,
admin_volunteer_roster, admin_qualifiers (×2), service_health_view, platform (×3),
qualifiers (×2), and the report tables in capacity (×2), crew (×2), insights (×3),
match_ops (×2), stream_rooms (×2), telemetry, volunteers.

**Exempt** — `# table-prefs: exempt` with a reason on the same line:

| Table | Reason |
|---|---|
| `admin_webhooks.py:92` header reference | Static 2-column documentation, already `mobile-grid: exempt` |
| `pages/auth.py:580` mock-Discord picker | Development-only user picker |
| `reports/shared.py` `paginated_event_log` (Audit Log, Telemetry) | Whole-`body` slot — cannot honour column order; **decomposed in wave 5**, exempt until then with a pointer to that wave |

Report tables keep their current `pagination=25`/`15` as the *default*; the
preference overrides it per person. That is the least surprising migration and
needs no decision per report.

## 3. The guardrail — `.claude/scripts/check_table_prefs.py` (new)

A sibling of `check_table_grid.py`, sharing its AST approach and its fail-open
posture. For every `ui.table(...)` in `pages/` / `theme/`, compliant when any
holds:

- `enable_mobile_grid(<table>, …, table_key=…)` is called on it;
- `customize_table(<table>, …)` is called on it;
- the construction line or the line above carries `table-prefs: exempt` / `noqa: table-prefs`.

Exit 2 with the fix, exit 0 otherwise. Register it in `.claude/settings.json`
beside `check_table_grid.py`, and add `check_table_prefs` to `CHECKS` in
`scripts/guardrails.py` so CI runs it too.

`tests/theme/test_table_preferences_coverage.py` — the source scan that CI cannot
skip:

| Test | Pins |
|---|---|
| `test_every_presentation_table_has_a_key_or_an_exemption` | the sweep is complete and stays complete |
| `test_every_table_key_is_declared_in_TableKeys` | no ad-hoc string keys |
| `test_table_keys_are_unique` | two tables sharing a key would trade columns |
| `test_every_exemption_carries_a_reason` | mirrors the `mobile-grid: exempt` convention |

## 4. Drag-to-reorder in the modal

Now that every table has the modal, upgrade the column list from ▲/▼ to
drag-and-drop (Quasar's `q-list` + `sortable` behaviour, or a `draggable`
attribute with a `dragover` handler — no new dependency).

**The ▲/▼ buttons stay.** They are the keyboard and touch path; drag is an
addition, never a replacement. A modal reachable only by mouse would be a
regression on a page whose whole point is accessibility of layout.

## 5. Seed data — `scripts/seed_dev.py`

Add a couple of `UserTablePreference` rows for the seeded staff user (idempotent
`get_or_create`, keyed on `(user, table_key)`): one hiding a column on
`admin.users`, one with a stored width on `admin.schedule`. Without these,
`/ui-validation` only ever exercises the defaults path, which is the path that
already works.

---

## Acceptance

- `python3 .claude/scripts/check_table_prefs.py` clean across the tree.
- `git grep -c "table_key=" pages/ theme/` matches the sweep list; every remaining `ui.table` has an exemption with a reason.
- `/ui-validation` sweep across four representative surfaces — an admin CRUD tab, a report, `/platform`, and a `MatchTableView` board — confirming the gear renders, saves and resets, and that the mobile cards are unchanged on each.
- No behaviour change on any table beyond the gear appearing. Wave 5 is where behaviour changes.
