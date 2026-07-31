# Wave 1 — Foundations

Model, migration, repository, service, the request-scoped cache and the pure
reconciler. **No visible change**: nothing imports `customize_table` yet.

Ships alone so the schema, the validation and the reconciliation rules can be
reviewed and tested without a pixel of UI in the diff.

---

## 1. Model — `models/preferences.py` (new)

```python
"""Per-user UI preferences that outlive a session.

Deliberately **global**, with no ``tenant`` FK. This is the ``User.timezone``
case: which columns a person wants on the Users board is a property of the
table, not of the community whose rows fill it, and someone who is staff in two
communities wants one answer rather than two. The practical consequence is that
there is no tenant column to scope, stamp, or leak-test.
"""

from tortoise import fields
from tortoise.models import Model


class UserTablePreference(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        'models.User', related_name='table_preferences', on_delete=fields.CASCADE)
    # Stable identifier for one table, e.g. ``admin.users``. Declared as a
    # constant in ``theme/tables/preferences.py`` so the guardrail can prove
    # uniqueness; stored here as an opaque string.
    table_key = fields.CharField(max_length=64)
    # Shape validated by TablePreferenceService.validate; column *names* are
    # reconciled in presentation, never here (see the plan's ground rule 4).
    config = fields.JSONField(default=dict)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('user', 'table_key'),)
```

Re-export `UserTablePreference` from `models/__init__.py` (alphabetical, in the
`from .preferences import ...` block).

**Migration:** `poetry run aerich migrate --name table_preferences && poetry run aerich upgrade`
→ `migrations/models/52_<ts>_table_preferences.py`. Commit both.

**Docs:** add the model to [`docs/reference/data-model.md`](../../reference/data-model.md)
with a one-line purpose and an explicit note that it is one of the deliberately
global models (alongside `User`, `Tenant`, `RacetimeBot`, `FeatureFlagGroup`).

---

## 2. Repository — `application/repositories/table_preference_repository.py` (new)

Plain static methods; **not** a `TenantScopedRepository`, for the same reason
`UserRepository` overrides its scoped methods — the model has no tenant column
and a scoped filter would raise. Say so in the docstring.

| Method | Signature | Note |
|---|---|---|
| `all_for_user` | `(user_id: int) -> dict[str, dict]` | **One query.** The only read the page build makes |
| `get` | `(user_id: int, table_key: str) -> Optional[UserTablePreference]` | |
| `upsert` | `(user_id: int, table_key: str, config: dict) -> UserTablePreference` | `update_or_create` on the unique pair |
| `delete` | `(user_id: int, table_key: str) -> bool` | Returns whether a row existed |
| `delete_all_for_user` | `(user_id: int) -> int` | "Reset every table" |

Export from `application/repositories/__init__.py`.

---

## 3. Request-scoped cache — `application/table_preferences_context.py` (new)

Copy the shape of [`application/timezone_context.py`](../../../application/timezone_context.py)
— a peer of `application/services`, import-safe from every layer, exempt from the
architecture hook. Its module docstring should state the same headline:
**resolution is async and hits the DB; reading it back is sync and free.**

```python
_prefs_var: ContextVar[Optional[dict[str, dict]]] = ContextVar(
    'wizzrobe_table_prefs', default=None)

def current_table_prefs() -> Optional[dict[str, dict]]:
    """The primed preference set, or ``None`` when nothing primed it."""

def table_prefs_for(table_key: str) -> Optional[dict]:
    """One table's stored config, or ``None`` (⇒ defaults)."""

@contextmanager
def table_prefs_scope(prefs: Optional[dict[str, dict]]) -> Iterator[None]:
    """Rebind a captured preference set — for lazy tab builds and background tasks."""
```

`None` means *unprimed*, and unprimed means *defaults*. There is no fallback
lookup, no client stash and no lazy DB read: a synchronous render must never
issue a query.

---

## 4. Service — `application/services/table_preference_service.py` (new)

```python
class TablePreferenceService:
    ALLOWED_PAGE_SIZES = (0, 10, 25, 50, 100)     # 0 == "All"
    ALLOWED_DENSITIES = ('comfortable', 'compact')
    MAX_COLUMNS   = 64
    MIN_WIDTH, MAX_WIDTH = 40, 1200
    MAX_NAME_LEN  = 64

    async def prime(self, user: Optional[User]) -> dict[str, dict]
    async def all_for_user(self, user: User) -> dict[str, dict]
    async def get(self, user: User, table_key: str) -> Optional[dict]
    async def save(self, user: User, table_key: str, config: Mapping) -> dict
    async def set_width(self, user: User, table_key: str, column: str,
                        width: Optional[int]) -> dict
    async def reset(self, user: User, table_key: str) -> None
    async def reset_all(self, user: User) -> None

    @staticmethod
    def validate(config: Mapping) -> dict          # pure; raises ValueError
```

**`validate`** is the whole security surface, since `config` arrives from a
browser. Reject, with a message a human could read:

- unknown top-level keys (allow exactly `columns`, `page_size`, `density`, `wrap`);
- `page_size` not in `ALLOWED_PAGE_SIZES`; `density` not in `ALLOWED_DENSITIES`; `wrap` not a bool;
- `columns` not a list, longer than `MAX_COLUMNS`, or containing a non-object;
- a column `name` that is not a `str`, is empty, or exceeds `MAX_NAME_LEN`;
- a duplicate `name`;
- `visible` not a bool; `width` neither `None` nor an int in `[MIN_WIDTH, MAX_WIDTH]`.

It returns a **normalised copy** — missing keys filled from the shipped defaults,
extra whitespace stripped — so what is stored is always canonical. Raise plain
`ValueError`; the UI catches it into `ui.notify(..., color='warning')` per the
coding conventions.

**`prime`** returns `{}` for `user is None` and does **not** write the
contextvar itself — the caller (`BaseLayout.render()`, wave 2) enters
`table_prefs_scope`. Keeping the service free of context manipulation is what
lets a test call it directly.

**`set_width`** is the drag path: read-modify-write of one column's `width`
inside the stored `config`. Two columns dragged in quick succession by the same
person can interleave; the loser is one column width, the row is never
corrupted, and the modal's Confirm rewrites the whole blob anyway. Note this in
the docstring rather than adding a lock.

**No audit row, no event.** State it in the module docstring so the next reader
does not "fix" it — `AuditActions` are `verb.object` records of changes to a
community's data, and column visibility is not one. `save` and `reset` instead
fire a best-effort `TelemetryService().track_interaction(event_type='table.preferences_saved', details={'table_key': ...})`,
which never raises, so adoption shows up in the existing Engagement report.

Export from `application/services/__init__.py`.

---

## 5. The reconciler — `theme/tables/preferences.py` (new, partial)

Wave 1 lands **only the pure function and the key constants**; `customize_table`
arrives in wave 2. No NiceGUI import in this half, so the tests are cheap.

```python
@dataclass(frozen=True)
class ColumnPlan:
    columns: list[dict]        # ordered, width/style applied, ready for table.columns
    visible: list[str]         # for the visible-columns prop
    page_size: int
    density: str
    wrap: bool
    is_customized: bool        # drives the gear's "modified" dot

DEFAULT_REQUIRED = frozenset({'actions', 'edit'})

def effective_columns(defaults: Sequence[Mapping],
                      saved: Optional[Mapping],
                      required: AbstractSet[str] = DEFAULT_REQUIRED) -> ColumnPlan
```

Rules, in order:

1. `saved is None` or empty ⇒ the defaults, unchanged, `is_customized=False`.
2. Saved entries are matched to defaults **by `name`**. A saved name with no default is dropped (a developer removed the column).
3. A default not named in `saved` is **appended at the end, visible** (ground rule 3).
4. Any column in `required` is forced `visible=True` regardless of what is stored — including one hidden by a previous version of the code.
5. If the result would have **no** visible non-required column, discard the saved config entirely and return defaults. An empty table is never the user's intent, and it is unrecoverable without a reset they cannot find.
6. A column with a `width` gets `style` and `headerStyle` of `width: {w}px` merged onto its dict (never mutating the caller's default dicts — copy).
7. `page_size` / `density` / `wrap` fall back to the table's shipped defaults when absent.

Also in this file, the key constants and their registry:

```python
TABLE_KEYS: Final = frozenset({ 'admin.users', 'admin.schedule', ... })
```

One frozen set, one place, so wave 4's guardrail can prove uniqueness and prove
that a key passed at a call site is declared.

---

## 6. Tests

`tests/theme/test_table_column_plan.py` — the pure function, no DB, no NiceGUI:

| Test | Pins |
|---|---|
| `test_no_saved_config_returns_defaults_unchanged` | rule 1 |
| `test_saved_order_is_honoured` | rule 2 |
| `test_a_saved_column_that_no_longer_exists_is_dropped` | rule 2 |
| `test_a_new_default_column_appears_for_a_user_who_saved_earlier` | **rule 3 — the one that ages** |
| `test_a_required_column_cannot_be_hidden` | rule 4 |
| `test_hiding_everything_falls_back_to_defaults` | rule 5 |
| `test_widths_become_style_and_header_style` | rule 6 |
| `test_default_column_dicts_are_not_mutated` | rule 6 — aliasing bug guard |

`tests/services/test_table_preference_service.py`:

| Test | Pins |
|---|---|
| `test_validate_rejects_unknown_keys` / `_bad_page_size` / `_out_of_range_width` / `_duplicate_column_names` / `_oversized_column_list` | every branch of `validate`, each asserting a `ValueError` |
| `test_validate_normalises_a_partial_config` | canonical storage |
| `test_save_is_upsert_idempotent` | no duplicate rows on the unique pair |
| `test_reset_removes_the_row_and_get_returns_none` | |
| `test_set_width_touches_one_column_only` | |
| `test_all_for_user_issues_one_query` | via the existing query-budget helper (`tests/test_query_budget.py`) |
| `test_prime_returns_empty_for_anonymous` | signed-out pages |
| `test_preferences_are_not_tenant_scoped` | the same user's config is returned under two different `tenant_scope`s — the decision, pinned |

---

## Acceptance

- `poetry run pytest tests/theme/test_table_column_plan.py tests/services/test_table_preference_service.py` green.
- `poetry run aerich upgrade` applies cleanly on a fresh DB, and the `migrations` CI job passes.
- `python3 scripts/guardrails.py` clean — in particular `enforce_architecture` (the service must not import `theme/`) and `check_tenant_scoping` (the new repository is deliberately unscoped and must be recognised as such; add it to the global-model allowance beside `UserRepository` if the check flags it).
- `git grep -n customize_table` returns nothing outside the plan. Wave 1 is invisible.
