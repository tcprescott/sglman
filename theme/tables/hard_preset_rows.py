"""Projecting a :class:`HardPresetState` onto a match-table row.

One place, because the row fields are written from three: the board's bulk load,
a single row refreshed after the dialog, and ``update_row_by_id`` carrying them
across a re-fetch. Three spellings of the same mapping is how a leak gets in —
the row dict is sent to the browser, so a field written here reaches whoever is
looking at the board.

Only the viewer's own state is ever written. ``_hard_agreed`` is the one field
that reports anybody else, and the service sets it only for a viewer who is
already part of the agreement.
"""

from typing import Any, Dict, Optional

from application.services import HardPresetState
from models import PresetOverride

HARD_PRESET_ROW_FIELDS = (
    '_hard_offered',
    '_hard_opted_in',
    '_hard_agreed',
    '_hard_locked',
    '_hard_override',
    '_hard_override_name',
    '_hard_name',
)


def apply_hard_preset_state(
    row: Dict[str, Any], state: Optional[HardPresetState],
) -> None:
    """Write ``state`` onto ``row``, or clear the fields when there is none."""
    if state is None or not state.offered:
        row['_hard_offered'] = False
        for field in HARD_PRESET_ROW_FIELDS[1:]:
            row[field] = '' if field.endswith('_name') else False
        return

    row['_hard_offered'] = True
    row['_hard_opted_in'] = state.opted_in
    row['_hard_agreed'] = state.everyone_in
    row['_hard_locked'] = state.locked
    row['_hard_override'] = state.override.value if state.override else ''
    row['_hard_override_name'] = (
        state.preset_name if state.override == PresetOverride.HARD
        else state.standard_preset_name or 'the standard settings'
        if state.override is not None else ''
    )
    row['_hard_name'] = state.preset_name


def carry_hard_preset_state(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    """Copy the row's hard-preset fields across a re-fetch of that row.

    The display service rebuilds a row from the match; these fields are the
    viewer's own and are not part of it, so without this a refreshed row loses
    its control.
    """
    for field in HARD_PRESET_ROW_FIELDS:
        target[field] = source.get(field, '' if field.endswith('_name') else False)
