"""How much crew approval is outstanding on a set of board rows.

A pending signup used to be communicated to staff by **text colour and nothing
else**: the words "pending", "awaiting approval" and "to approve" appeared
nowhere on the Schedule board, and `.st-pending` — its only marker — is the same
class the overdue-timestamp cell uses, so most elements carrying it on a given
board were not crew at all. The one surface that could *find* the work (Reports
→ Crew Activity, with its Pending-only filter) could not act on it.

Counting here rather than in the page for the reason ``match_labels`` gives:
it is pure string-and-dict work over rows the board already holds, so it needs
no query, and it can be tested without a browser.
"""

from dataclasses import dataclass, field
from typing import Iterable, Sequence

#: The row keys carrying crew, and the singular each reads as in the strip.
CREW_KEYS = (('commentators', 'commentator'), ('trackers', 'tracker'))


@dataclass(frozen=True)
class PendingCrew:
    """Signups awaiting a decision across one board's visible rows."""

    commentators: int = 0
    trackers: int = 0
    match_ids: tuple = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return self.commentators + self.trackers

    @property
    def label(self) -> str:
        """"3 commentators and 1 tracker awaiting approval"; empty when none.

        Names the roles rather than a bare number because the two are staffed by
        different people and a coordinator triages them differently.
        """
        parts = [
            f'{count} {noun}{"" if count == 1 else "s"}'
            for count, noun in ((self.commentators, 'commentator'), (self.trackers, 'tracker'))
            if count
        ]
        if not parts:
            return ''
        return ' and '.join(parts) + ' awaiting approval'


def pending_crew_summary(rows: Iterable[dict]) -> PendingCrew:
    """Count unapproved crew signups over ``rows``, newest board order kept.

    A row's crew entries are the dicts ``MatchDisplayService`` builds, each with
    an ``approved`` flag. A **cancelled or confirmed** match is skipped: its crew
    is no longer a decision anyone needs to make, and counting it would keep a
    queue permanently non-empty.
    """
    counts = {'commentators': 0, 'trackers': 0}
    match_ids: list = []
    for row in rows:
        if row.get('state') in ('Confirmed', 'Cancelled'):
            continue
        row_has_pending = False
        for key, _noun in CREW_KEYS:
            for item in _crew_items(row.get(key)):
                if not item.get('approved'):
                    counts[key] += 1
                    row_has_pending = True
        if row_has_pending and row.get('id') is not None:
            match_ids.append(row['id'])
    return PendingCrew(
        commentators=counts['commentators'],
        trackers=counts['trackers'],
        match_ids=tuple(match_ids),
    )


def _crew_items(value) -> Sequence[dict]:
    if not isinstance(value, (list, tuple)):
        return ()
    return [item for item in value if isinstance(item, dict)]
