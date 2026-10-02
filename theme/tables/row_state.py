"""Viewer-stamped match-row fields, carried across a single-row re-fetch.

``MatchTableView.refresh`` stamps each row with fields that belong to the viewer
rather than the match: ``_watching``, ``_stream_volunteer``, ``_can_reschedule``,
``_reschedule_pending``, the ``_hard_*`` family. ``update_row_by_id`` rebuilds
one row from the display service, which knows nothing of them, so every field it
does not carry is silently dropped from that row until the next full refresh.

It used to carry a hand-kept list, and the list fell behind: acknowledging a
match, or any ``match_live`` flash, removed the row's Ask to change button. The
convention is now the contract: a leading underscore marks a viewer-stamped
field, and every one is carried unless the fresh row already sets it.
"""

from typing import Any, Dict

# Per-update effects rather than viewer state: carrying one would replay it.
TRANSIENT_ROW_FIELDS = frozenset({'_flash'})


def carry_viewer_row_state(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    """Copy each ``_``-prefixed field of ``source`` that ``target`` does not set."""
    for key, value in source.items():
        if key.startswith('_') and key not in TRANSIENT_ROW_FIELDS and key not in target:
            target[key] = value
