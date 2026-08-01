"""Per-user table layouts — the reconciler between shipped defaults and saved config.

A table's columns are declared in code; a person's preferences are a *filter over*
that declaration, never a replacement for it. :func:`effective_columns` is where
the two meet, and it is deliberately pure: no NiceGUI, no DB, no context — just
the shipped column dicts, the stored blob, and the rules below.

The single most important rule is rule 3: **a default column the user has never
seen is appended, visible.** The opposite (honour the saved list exactly) makes
every newly added column invisible forever to everyone who has ever opened the
Preferences gear, and it is a bug that surfaces months later as a support ticket.

Column *names* are reconciled here rather than in
:class:`~application.services.TablePreferenceService`, because the authoritative
list lives in presentation and a service importing ``theme/`` would invert the
architecture. An unknown stored name is dropped silently at render time — that is
the mechanism for a developer deleting a column, not an error.
"""

from dataclasses import dataclass, field
from typing import AbstractSet, Any, Final, Mapping, Optional, Sequence

__all__ = ['DEFAULT_REQUIRED', 'TABLE_KEYS', 'ColumnPlan', 'TableKeys',
           'effective_columns']

# Columns a person may not hide: the row-action cells. Hiding them strands every
# row action behind no affordance at all, and the way back is a reset the user
# cannot find because the gear that offers it is in the toolbar, not the row.
DEFAULT_REQUIRED: Final[frozenset[str]] = frozenset({'actions', 'edit'})


class TableKeys:
    """Every table's stable preference key, namespaced ``surface.table``.

    One place, so a key cannot be invented at a call site and two tables cannot
    quietly share one (which would have them trade column layouts).
    """

    ADMIN_USERS = 'admin.users'
    ADMIN_SCHEDULE = 'admin.schedule'
    ADMIN_TOURNAMENTS = 'admin.tournaments'
    HOME_SCHEDULE = 'home.schedule'
    HOME_PLAYER_MATCHES = 'home.player_matches'
    PROCTOR_STATION = 'volunteer.proctor_station'


def _declared_keys() -> frozenset[str]:
    return frozenset(
        value for name, value in vars(TableKeys).items()
        if not name.startswith('_') and isinstance(value, str)
    )


TABLE_KEYS: Final[frozenset[str]] = _declared_keys()


@dataclass(frozen=True)
class ColumnPlan:
    """What one table should paint for one viewer."""

    columns: list[dict]        # ordered, width/style applied, ready for table.columns
    visible: list[str]         # for Quasar's visible-columns prop
    page_size: int
    density: str
    wrap: bool
    is_customized: bool        # drives the gear's "modified" dot
    widths: dict[str, int] = field(default_factory=dict)

    @property
    def has_widths(self) -> bool:
        """Whether any column carries a stored width (⇒ fixed table layout)."""
        return bool(self.widths)


def _merge_style(existing: Any, addition: str) -> str:
    existing = (existing or '').strip()
    if not existing:
        return addition
    if not existing.endswith(';'):
        existing += ';'
    return f'{existing} {addition}'


def _signature(columns: Sequence[Mapping], visible: Sequence[str],
               widths: Mapping[str, int]) -> list[tuple]:
    return [
        (c.get('name'), c.get('name') in visible, widths.get(c.get('name')))
        for c in columns
    ]


def effective_columns(
    defaults: Sequence[Mapping],
    saved: Optional[Mapping],
    required: AbstractSet[str] = DEFAULT_REQUIRED,
    *,
    page_size: int = 0,
    density: str = 'comfortable',
    wrap: bool = False,
) -> ColumnPlan:
    """Reconcile a stored layout against the columns the code ships today.

    Rules, in order:

    1. No saved config ⇒ the defaults, unchanged, ``is_customized=False``.
    2. Saved entries match defaults **by name**; a saved name with no default is
       dropped (a developer removed the column).
    3. A default not named in the saved list is **appended at the end**, at its
       shipped visibility — visible unless the column declares ``hidden``.
    4. Any column in ``required`` is forced visible, whatever is stored.
    5. If nothing non-required would remain visible, the saved config is
       discarded wholesale. An empty table is never the intent, and it is
       unrecoverable without a reset the user cannot reach.
    6. A stored ``width`` becomes ``style`` / ``headerStyle`` on a **copy** of the
       default dict — the caller's module-level column lists are never mutated.
    7. ``page_size`` / ``density`` / ``wrap`` fall back to this table's shipped
       values when the stored config does not carry them.
    """
    shipped = [dict(c) for c in defaults]
    default_visible = [
        c.get('name', '') for c in shipped if not c.get('hidden')]
    fallback = ColumnPlan(
        columns=shipped,
        visible=default_visible,
        page_size=page_size,
        density=density,
        wrap=wrap,
        is_customized=False,
    )

    if not saved or not isinstance(saved, Mapping):
        return fallback

    by_name: dict[str, dict] = {}
    for col in shipped:
        by_name.setdefault(col.get('name', ''), col)

    saved_columns = saved.get('columns')
    ordered: list[tuple[dict, Optional[Mapping]]] = []
    seen: set[str] = set()
    if isinstance(saved_columns, (list, tuple)):
        for entry in saved_columns:
            if not isinstance(entry, Mapping):
                continue
            name = entry.get('name')
            if not isinstance(name, str) or name in seen or name not in by_name:
                continue
            seen.add(name)
            ordered.append((by_name[name], entry))
    for col in shipped:
        name = col.get('name', '')
        if name not in seen:
            seen.add(name)
            ordered.append((col, None))

    columns: list[dict] = []
    visible: list[str] = []
    widths: dict[str, int] = {}
    for col, entry in ordered:
        out = dict(col)
        name = out.get('name', '')

        if entry is None:
            is_visible = not col.get('hidden')
        else:
            is_visible = bool(entry.get('visible', True))
        if name in required:
            is_visible = True

        width = entry.get('width') if entry is not None else None
        if isinstance(width, int) and not isinstance(width, bool) and width > 0:
            widths[name] = width
            out['style'] = _merge_style(out.get('style'), f'width: {width}px')
            out['headerStyle'] = _merge_style(out.get('headerStyle'), f'width: {width}px')

        # Keep the app's own ``hidden`` convention in step with the plan so the
        # card builder and visible-columns never disagree about one column.
        if is_visible:
            out.pop('hidden', None)
            visible.append(name)
        else:
            out['hidden'] = True

        columns.append(out)

    if not [n for n in visible if n not in required]:
        return fallback

    resolved_page_size = page_size
    stored_page_size = saved.get('page_size')
    if isinstance(stored_page_size, int) and not isinstance(stored_page_size, bool):
        resolved_page_size = stored_page_size

    resolved_density = density
    if isinstance(saved.get('density'), str):
        resolved_density = saved['density']

    resolved_wrap = wrap
    if isinstance(saved.get('wrap'), bool):
        resolved_wrap = saved['wrap']

    is_customized = (
        _signature(columns, visible, widths)
        != _signature(shipped, default_visible, {})
        or resolved_page_size != page_size
        or resolved_density != density
        or resolved_wrap != wrap
    )

    return ColumnPlan(
        columns=columns,
        visible=visible,
        page_size=resolved_page_size,
        density=resolved_density,
        wrap=resolved_wrap,
        is_customized=is_customized,
        widths=widths,
    )
