"""Generic mobile grid (card) support for admin / report ``ui.table``s.

Below Quasar's ``lt.md`` breakpoint a wide HTML table overflows a phone: columns
and every row-action button slide off the right edge behind a horizontal scroll.
The app's fix is to flip the table into Quasar *grid* mode
(``:grid="Quasar.Screen.lt.md"``) and register an ``item`` slot that stacks each
row as a card. The four purpose-built family tables (match, user, tournament,
equipment) ship bespoke cards (see ``match_grid.py``); **every other**
admin/report/player table should get its responsive card from this one helper so
the pattern stays uniform — and so the ``check_table_grid`` guardrail can prove a
new table has one.

``enable_mobile_grid`` is column-driven (the same technique
``match_grid.render_grid_slot`` uses): it walks the ``columns`` list the desktop
table already uses, skips ``hidden`` and the ``actions`` column, and emits a
``.sgl-grid-card`` with a ``label / value`` row per remaining column plus an
optional right-aligned actions footer. A field that renders as a badge / chip /
icon on the desktop (via a ``body-cell-<field>`` slot) can pass a matching card
snippet through ``field_slots`` — Vue that reads ``props.row.<field>`` (note:
``props.row``, not the ``props.value`` the desktop cell slot sees). Anything
omitted falls back to the plain ``{{ props.row.<field> }}`` value.

Presentation-only: builds NiceGUI/Vue slot strings, no business logic.
"""

import html
from typing import Mapping, Optional, Sequence

from nicegui import ui

__all__ = ['MOBILE_GRID_BREAKPOINT', 'enable_mobile_grid']

# Quasar Screen breakpoint below which the table switches to card/grid mode.
# ``lt.md`` (<1024px) is the app default; the match table lets callers widen it
# to ``lt.lg`` on its densest pages.
MOBILE_GRID_BREAKPOINT = 'lt.md'


def _value_html(name: str, field: str, field_slots: Mapping[str, str]) -> str:
    """The card cell body for one column: a caller override or the raw value.

    ``field_slots`` may be keyed by column ``name`` or by ``field`` (they usually
    match); ``name`` wins when both are present.
    """
    if name in field_slots:
        return field_slots[name]
    if field in field_slots:
        return field_slots[field]
    return '{{ props.row.' + field + ' }}'


def enable_mobile_grid(
    table: ui.table,
    columns: Sequence[Mapping],
    *,
    actions: str = '',
    field_slots: Optional[Mapping[str, str]] = None,
    row_click_event: Optional[str] = None,
    breakpoint: str = MOBILE_GRID_BREAKPOINT,
) -> ui.table:
    """Make ``table`` render as stacked cards below ``breakpoint``.

    Adds the ``:grid`` prop and an ``item`` slot generated from ``columns``.
    Returns ``table`` so the call can chain.

    Args:
        table: the ``ui.table`` to make responsive.
        columns: the same column dicts passed to the table. ``hidden`` columns
            and the ``actions`` column are skipped in the card body.
        actions: raw inner HTML for the card's actions footer — typically the
            **same** row-action ``q-btn``s used in the ``body-cell-actions``
            slot (they emit ``$parent.$emit('event', props.row)`` and work
            unchanged inside the card). Empty ⇒ no footer.
        field_slots: optional ``{column_name: vue_snippet}`` overrides for
            fields that render as a badge/chip/icon; the snippet reads
            ``props.row.<field>``.
        row_click_event: when a desktop table wires a whole-row drill-down,
            pass its event name so the card is tappable too (emits
            ``$parent.$emit('<event>', props.row)``). Do not combine with
            ``actions`` — a button tap would also bubble the card click.
        breakpoint: Quasar Screen breakpoint (default ``lt.md``).
    """
    field_slots = field_slots or {}
    table.props(f':grid="Quasar.Screen.{breakpoint}"')

    rows: list[str] = []
    for col in columns:
        name = col.get('name', '')
        if name == 'actions' or col.get('hidden'):
            continue
        field = col.get('field', name)
        if not isinstance(field, str):
            field = name
        label = html.escape(str(col.get('label', name) or ''))
        rows.append(
            '<div class="row items-center q-mb-xs">'
            f'<div class="col-5 text-grey-7 text-caption">{label}</div>'
            '<div class="col-7" style="overflow-wrap:anywhere">'
            f'{_value_html(name, field, field_slots)}</div>'
            '</div>'
        )

    footer = (
        f'<div class="row items-center justify-end q-gutter-x-sm q-mt-sm">{actions}</div>'
        if actions.strip() else ''
    )

    if row_click_event:
        card_open = (
            '<q-card bordered flat class="q-pa-sm sgl-grid-card cursor-pointer" '
            f'@click="$parent.$emit(\'{row_click_event}\', props.row)">'
        )
    else:
        card_open = '<q-card bordered flat class="q-pa-sm sgl-grid-card">'

    table.add_slot(
        'item',
        '<div class="q-pa-xs col-xs-12 col-sm-6">'
        + card_open
        + ''.join(rows) + footer +
        '</q-card></div>',
    )
    return table
