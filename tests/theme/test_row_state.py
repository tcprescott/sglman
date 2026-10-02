"""``update_row_by_id`` keeps every viewer-stamped field across a re-fetch.

Acknowledging a match on the web re-fetched its row, and the hand-kept carry list
did not include ``_can_reschedule``/``_reschedule_pending``, so the row lost its
Ask to change button until a reload (docs/reviews/player-journey-ux.md F4).
"""

from pathlib import Path

from theme.tables.row_state import carry_viewer_row_state

REPO = Path(__file__).resolve().parents[2]


def test_every_underscore_field_is_carried():
    old = {
        'id': 7, 'state': 'Scheduled',
        '_watching': True, '_stream_volunteer': False,
        '_can_reschedule': True, '_reschedule_pending': False,
        '_hard_offered': True, '_hard_name': 'Hard',
        '_some_future_field': 'kept',
    }
    fresh = {'id': 7, 'state': 'Scheduled'}
    carry_viewer_row_state(fresh, old)
    for key, value in old.items():
        assert fresh[key] == value, key


def test_fresh_values_win_and_the_flash_is_not_replayed():
    old = {'id': 7, '_flash': True, '_watching': False, 'state': 'Scheduled'}
    fresh = {'id': 7, '_watching': True, 'state': 'Started'}
    carry_viewer_row_state(fresh, old)
    assert fresh['_watching'] is True
    assert fresh['state'] == 'Started'
    assert '_flash' not in fresh


def test_update_row_by_id_uses_the_generic_carry():
    source = (REPO / 'theme' / 'tables' / 'match.py').read_text()
    body = source[source.index('async def update_row_by_id'):]
    body = body[:body.index('\n    def ', 1)]
    assert 'carry_viewer_row_state(match_data, self.table.rows[idx])' in body
