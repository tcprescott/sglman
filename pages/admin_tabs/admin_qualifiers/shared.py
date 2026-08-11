"""Constants, pure helpers and table definitions for the Async Qualifiers admin.

Nothing here touches a service or the ORM. The drill-down's tab names live here
because both ``page``'s loaders and its views key on them; the paging constants
because the bug they exist to prevent is a table built without one.
"""

from typing import Any, Dict, Mapping, Sequence

from application.utils.duration import format_hms
from application.utils.timezone import format_local_display

__all__ = [
    'BOARD_COLUMNS',
    'BOARD_PAGE',
    'BOARD_TAB',
    'GRANTABLE_STATUSES',
    'GRANT_ACTION',
    'LIVE_TAB',
    'POOLS_TAB',
    'POOL_PERMALINK_PREVIEW',
    'QUEUE_PAGE_SIZE',
    'QUEUE_TAB',
    'RUNS_COLUMNS',
    'RUNS_PAGE',
    'RUNS_TAB',
    'board_rows',
    'enum_value',
    'existing_notes',
    'fmt',
    'live_race_color',
    'other_runs_summary',
    'run_rows',
    'short_url',
]


def fmt(dt) -> str:
    return format_local_display(dt) if dt else '—'


def enum_value(value: Any) -> str:
    return value.value if hasattr(value, 'value') else str(value)


# Terminal run states a reattempt can be granted on — an in-progress run is
# finished or forfeited first.
GRANTABLE_STATUSES = {'finished', 'forfeit', 'disqualified'}

# The drill-down's tabs, by name rather than by element: the name is what
# ``state['tab']`` carries across a rebuild, and what each per-tab loader is keyed
# on. A refreshable detail view resets its panel to the default on every rebuild,
# so without this a reviewer is thrown out of the queue after each verdict.
POOLS_TAB = 'Pools'
LIVE_TAB = 'Live Races'
QUEUE_TAB = 'Review Queue'
RUNS_TAB = 'Runs'
BOARD_TAB = 'Leaderboard'

# Client-side paging over rows already loaded, matching the family boards. Absent
# a pagination prop, ``page_size`` resolves to 0 — Quasar's "every row" — and a
# real qualifier's Runs tab renders thousands of rows into a single page.
RUNS_PAGE = {'rowsPerPage': 25, 'page': 1}
BOARD_PAGE = {'rowsPerPage': 50, 'page': 1}
# The review queue is cards rather than a table, so it cannot page: it renders
# this many and offers the rest behind a control. Working a queue is a
# front-to-back job, so the tail is the part nobody is looking at yet.
QUEUE_PAGE_SIZE = 20
# A pool's permalinks are a plain list of links. Past this many the Pools tab is
# scrolling rather than showing, so the tail goes behind an expansion.
POOL_PERMALINK_PREVIEW = 10

# ``v-if`` on the row's own flag: a voided or in-progress run offers nothing.
GRANT_ACTION = '''
    <q-btn v-if="props.row.grantable" flat dense icon="restart_alt" color="primary"
           label="Grant reattempt"
           @click="$parent.$emit('grant', props.row)">
        <q-tooltip>Void this run and free its pool slot</q-tooltip>
    </q-btn>
'''

RUNS_COLUMNS: Sequence[Dict[str, Any]] = [
    {'name': 'player', 'label': 'Player', 'field': 'player', 'align': 'left',
     'sortable': True},
    {'name': 'pool', 'label': 'Pool', 'field': 'pool', 'align': 'left',
     'sortable': True},
    {'name': 'status', 'label': 'Status', 'field': 'status', 'sortable': True},
    {'name': 'review', 'label': 'Review', 'field': 'review', 'sortable': True},
    # HH:MM:SS is zero-padded, so a lexical sort is a chronological one.
    {'name': 'claimed', 'label': 'Claimed', 'field': 'claimed', 'sortable': True},
    {'name': 'timed', 'label': 'Timed', 'field': 'timed', 'sortable': True},
    {'name': 'score', 'label': 'Score', 'field': 'score', 'sortable': True},
    {'name': 'actions', 'label': '', 'field': 'actions'},
]

BOARD_COLUMNS: Sequence[Dict[str, Any]] = [
    {'name': 'rank', 'label': '#', 'field': 'rank', 'sortable': True},
    {'name': 'user', 'label': 'Player', 'field': 'user', 'align': 'left',
     'sortable': True},
    {'name': 'actual', 'label': 'Score', 'field': 'actual', 'sortable': True},
    {'name': 'estimate', 'label': 'Estimate', 'field': 'estimate', 'sortable': True},
    # Not sortable: 'filled/total' is a composite, and 2/9 would sort above 10/10.
    {'name': 'slots', 'label': 'Slots', 'field': 'slots'},
]


def run_rows(runs) -> list:
    """The admin Runs tab's rows — every run, because a forfeit never reaches the
    review queue and this is the only place a mis-clicked one can be found."""
    return [
        {
            'id': run.id,
            'player': run.user.display_name or run.user.username,
            'pool': (run.permalink.pool.name if run.permalink and run.permalink.pool else '—'),
            'status': enum_value(run.status) + (' (voided)' if run.reattempted else ''),
            'review': enum_value(run.review_status),
            'claimed': format_hms(run.elapsed_seconds),
            'timed': format_hms(run.measured_seconds),
            'score': '' if run.score is None else round(run.score, 1),
            'grantable': (not run.reattempted
                          and enum_value(run.status) in GRANTABLE_STATUSES),
        }
        for run in runs
    ]


def board_rows(entries) -> list:
    return [
        {'rank': i + 1, 'user': e.username, 'actual': e.actual,
         'estimate': e.estimate, 'slots': f'{e.slots_filled}/{e.slots_total}'}
        for i, e in enumerate(entries)
    ]


def short_url(url: str, limit: int = 60) -> str:
    url = url or ''
    return url if len(url) <= limit else f'{url[:limit]}…'


def other_runs_summary(tally: Mapping[int, Mapping[str, int]], run) -> str:
    """"Player Two: 2 other runs in this qualifier (1 approved, 1 forfeit)".

    Re-reviewing without seeing a runner's other attempts is how two reviewers
    reach different conclusions about the same person.

    ``tally`` is the per-runner outcome count from
    ``AsyncQualifierService.review_queue_context``, which counts *every* run
    including this one — so this run's own outcome is subtracted here rather than
    filtered in the query, keeping the read a plain grouped count.
    """
    counts = dict(tally.get(run.user_id, {}))
    if not counts:
        return ''
    own = ('voided' if run.reattempted
           else enum_value(run.review_status) if enum_value(run.status) == 'finished'
           else enum_value(run.status))
    if counts.get(own):
        counts[own] -= 1
    counts = {label: n for label, n in counts.items() if n > 0}
    total = sum(counts.values())
    if not total:
        return ''
    breakdown = ', '.join(f'{n} {label}' for label, n in sorted(counts.items()))
    runner = run.user.display_name or run.user.username
    plural = '' if total == 1 else 's'
    return f'{runner}: {total} other run{plural} in this qualifier ({breakdown})'


def existing_notes(run) -> list:
    notes = list(getattr(run, 'review_notes', []) or [])
    return [n.note for n in notes if getattr(n, 'note', '')]


def live_race_color(status) -> str:
    return {
        'scheduled': 'grey',
        'pending': 'blue',
        'in_progress': 'orange',
        'finished': 'green',
    }.get(enum_value(status), 'grey')
