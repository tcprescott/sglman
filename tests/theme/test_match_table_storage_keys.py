"""Each match board owns its filters — they are not a single shared setting.

Four ``MatchTableView`` instances (home schedule, player dashboard, admin
schedule, proctor board) live in one browser session. They used to persist
``state_filter`` / ``tournament_filter`` / ``stream_room_filter`` under those
bare names, so changing the State filter on the admin Schedule tab silently
retargeted the proctor station and both home boards — and whichever board was
visited last overwrote every per-board default. ``_skey`` namespaces the keys
per view; these tests pin that derivation and the per-view default.

Constructing the view for real needs a NiceGUI slot context, so the tests build
it with ``__new__`` and set only the attributes under test.
"""

import ast
import inspect
from pathlib import Path

from theme.tables.match import DEFAULT_STATE_FILTER, MatchTableView

REPO = Path(__file__).resolve().parents[2]

# Every construction site, and the storage_key it must pass. A board missing
# from this map is a board sharing someone else's filters.
CONSTRUCTION_SITES = {
    'pages/admin_tabs/admin_schedule.py': 'admin_schedule',
    'pages/volunteer_tabs/proctor_station.py': 'proctor',
    'pages/home_tabs/schedule.py': 'home_schedule',
    'pages/home_tabs/player.py': 'player_dashboard',
}


def _view(storage_key='match', default_state_filter=None):
    view = MatchTableView.__new__(MatchTableView)
    view.storage_key = storage_key
    view.default_state_filter = default_state_filter
    return view


def test_two_views_do_not_share_a_filter_key():
    a = _view('admin_schedule')
    b = _view('proctor')
    assert a._skey('state_filter') != b._skey('state_filter')


def test_every_filter_key_is_namespaced_by_the_view():
    view = _view('proctor')
    for name in ('state_filter', 'tournament_filter', 'stream_room_filter'):
        assert view._skey(name).startswith('proctor:')
        assert view._skey(name) != name


def test_skey_keeps_the_filter_names_distinct_within_a_view():
    view = _view('admin_schedule')
    keys = {view._skey(n) for n in
            ('state_filter', 'tournament_filter', 'stream_room_filter')}
    assert len(keys) == 3


def test_no_bare_session_key_survives_in_the_view():
    """The whole bug was un-namespaced ``tenant_session_*`` calls."""
    src = inspect.getsource(MatchTableView)
    for name in ('state_filter', 'tournament_filter', 'stream_room_filter'):
        for call in ('tenant_session_get', 'tenant_session_set'):
            assert f"{call}('{name}'" not in src, (
                f"{call}('{name}') is not namespaced — every board would share it; "
                f"use self._skey('{name}')"
            )


def _storage_key_arg(path: str):
    """The literal ``storage_key=`` passed to MatchTableView(...) in ``path``."""
    tree = ast.parse((REPO / path).read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == 'MatchTableView'):
            continue
        for kw in node.keywords:
            if kw.arg == 'storage_key':
                return ast.literal_eval(kw.value)
        return None
    raise AssertionError(f'no MatchTableView(...) construction found in {path}')


def test_each_board_passes_its_own_storage_key():
    for path, expected in CONSTRUCTION_SITES.items():
        assert _storage_key_arg(path) == expected, (
            f'{path} must pass storage_key={expected!r}'
        )


def test_the_four_storage_keys_are_distinct():
    keys = list(CONSTRUCTION_SITES.values())
    assert len(set(keys)) == len(keys)


# --- default_state_filter ----------------------------------------------------

def test_default_state_filter_is_used_when_nothing_is_stored(monkeypatch):
    stored = {}
    monkeypatch.setattr('theme.tables.match.tenant_session_get',
                        lambda key, default=None: stored.get(key, default))
    view = _view('admin_schedule', ['Scheduled', 'Finished'])
    assert view._stored_or_default_states() == ['Scheduled', 'Finished']


def test_shared_default_applies_when_the_view_declares_none(monkeypatch):
    monkeypatch.setattr('theme.tables.match.tenant_session_get',
                        lambda key, default=None: default)
    view = _view('proctor', None)
    assert view._stored_or_default_states() == list(DEFAULT_STATE_FILTER)


def test_a_stored_value_beats_the_default(monkeypatch):
    stored = {'admin_schedule:state_filter': ['Confirmed']}
    monkeypatch.setattr('theme.tables.match.tenant_session_get',
                        lambda key, default=None: stored.get(key, default))
    view = _view('admin_schedule', ['Scheduled', 'Finished'])
    assert view._stored_or_default_states() == ['Confirmed']


def test_another_boards_stored_value_does_not_leak(monkeypatch):
    """The regression that matters: the proctor board keeps its own default
    even after the admin board stored something else."""
    stored = {'admin_schedule:state_filter': ['Confirmed']}
    monkeypatch.setattr('theme.tables.match.tenant_session_get',
                        lambda key, default=None: stored.get(key, default))
    assert _view('proctor')._stored_or_default_states() == list(DEFAULT_STATE_FILTER)


# --- the mobile filter-count badge ------------------------------------------

class _FakeSelect:
    def __init__(self, value):
        self.value = value


def test_badge_does_not_count_a_boards_own_default_as_a_custom_filter():
    view = _view('admin_schedule', ['Scheduled', 'Checked In', 'Started', 'Finished'])
    view.tournament_filter = None
    view.stream_room_filter = None
    view.state_filter = _FakeSelect(['Finished', 'Started', 'Checked In', 'Scheduled'])
    assert view._active_filter_count() == 0


def test_badge_counts_a_state_filter_moved_off_the_boards_default():
    view = _view('admin_schedule', ['Scheduled', 'Checked In', 'Started', 'Finished'])
    view.tournament_filter = None
    view.stream_room_filter = None
    view.state_filter = _FakeSelect(['Finished'])
    assert view._active_filter_count() == 1
