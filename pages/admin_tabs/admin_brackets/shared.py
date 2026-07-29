"""Helpers shared by the bracket admin's page and its three dialogs.

Datetime marshalling for the native ``datetime-local`` inputs, round labelling,
and the entry-id → display-name map the results and advance dialogs both need.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from application.utils.timezone import parse_eastern_datetime, to_eastern
from models import BracketFormat, BracketMatch

ELIM_FORMATS = (BracketFormat.SINGLE_ELIM, BracketFormat.DOUBLE_ELIM)


def iso_to_local_input(iso: Optional[str]) -> str:
    """Stored UTC ISO → a ``datetime-local`` value (Eastern) for prefill."""
    if not iso:
        return ''
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ''
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return to_eastern(dt).strftime('%Y-%m-%dT%H:%M')


def local_input_to_iso(value: Optional[str]) -> Optional[str]:
    """A ``datetime-local`` value (Eastern) → stored UTC ISO, or None if blank."""
    if not value or 'T' not in value:
        return None
    date_str, time_str = value.split('T', 1)
    return parse_eastern_datetime(date_str, time_str[:5]).isoformat()


def distinct_rounds(matches: List[BracketMatch]) -> List[int]:
    """Rounds present, ordered winners (asc) then losers (by magnitude)."""
    positive = sorted({m.round for m in matches if m.round >= 0})
    negative = sorted({m.round for m in matches if m.round < 0}, key=abs)
    return positive + negative


def round_editor_label(round_number: int) -> str:
    if round_number < 0:
        return f'Losers Round {abs(round_number)}'
    return f'Round {round_number}'


async def entry_name_map(service, bracket_id: int, tournament_id: int) -> Dict[int, str]:
    """entry_id → entrant display name (the caller supplies the tenant scope)."""
    entrants = {
        en.id: en.display_name for en in await service.list_entrants(tournament_id)
    }
    entries = await service.list_entries(bracket_id)
    return {e.id: entrants.get(e.entrant_id, f'Entry {e.id}') for e in entries}
