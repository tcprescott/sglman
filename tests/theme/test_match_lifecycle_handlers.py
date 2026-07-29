"""The admin Schedule tab and the proctor board share one set of lifecycle callbacks.

Copying the handler bodies into a second page would guarantee drift, so both
surfaces build their ``MatchTableView`` from ``MatchLifecycleHandlers``. These
tests pin the contract (``can_crud`` gating by *omission*, not ``None``) and the
fact that neither page re-implements it.
"""

import inspect

import pages.admin_tabs.admin_schedule as admin_schedule
import pages.volunteer_tabs.proctor_station as proctor_station
from theme.tables.match_lifecycle import MatchLifecycleHandlers

LIFECYCLE = ['on_generate_seed', 'on_seat', 'on_start', 'on_finish', 'on_assign_stations']
CRUD_ONLY = ['on_edit', 'on_confirm', 'on_edit_stream_room']


def test_every_viewer_gets_the_lifecycle_callbacks():
    cb = MatchLifecycleHandlers(None, can_crud=False).callbacks()
    assert set(LIFECYCLE) <= set(cb)


def test_crud_only_callbacks_are_omitted_not_none():
    """MatchTableView keys slot registration off *presence*, so None would show the control."""
    cb = MatchLifecycleHandlers(None, can_crud=False).callbacks()
    for name in CRUD_ONLY:
        assert name not in cb


def test_crud_viewer_gets_all_eight():
    cb = MatchLifecycleHandlers(None, can_crud=True).callbacks()
    assert set(cb) == set(LIFECYCLE) | set(CRUD_ONLY)
    assert all(callable(fn) for fn in cb.values())


def test_both_surfaces_build_their_view_from_the_shared_handlers():
    for module, fn in ((admin_schedule, admin_schedule.admin_schedule_page),
                       (proctor_station, proctor_station.proctor_station_tab)):
        src = inspect.getsource(fn)
        assert 'MatchLifecycleHandlers(' in src, module.__name__
        assert '**handlers.callbacks()' in src, module.__name__
        assert 'handlers.table_view = table_view' in src, module.__name__


def test_the_proctor_board_never_offers_crud():
    src = inspect.getsource(proctor_station.proctor_station_tab)
    assert 'can_crud=False' in src
    assert 'submit_match_callback' not in src
