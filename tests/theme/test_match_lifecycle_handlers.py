"""The admin Schedule tab and the proctor board share one set of lifecycle callbacks.

Copying the handler bodies into a second page would guarantee drift, so both
surfaces build their ``MatchTableView`` from ``MatchLifecycleHandlers``. These
tests pin the contract — gating by *omission* rather than ``None``, one group per
``MatchBoardAccess`` capability — and the fact that neither page re-implements
it.

The capability split is the point: the board used to pass the five run callbacks
to *everyone* and gate only the other four, which is how a crew coordinator was
handed Check In, Start, Generate and Stations buttons that ``can_run_match`` then
refused one click later.
"""

import inspect

import pages.admin_tabs.admin_schedule as admin_schedule
import pages.volunteer_tabs.proctor_station as proctor_station
from theme.tables.match_access import MatchBoardAccess
from theme.tables.match_lifecycle import MatchLifecycleHandlers

RUN = ['on_generate_seed', 'on_seat', 'on_start', 'on_finish', 'on_assign_stations']
EDIT = ['on_edit']
CONFIRM = ['on_confirm', 'on_edit_result']
STREAM = ['on_edit_stream_room']
ALL = RUN + EDIT + CONFIRM + STREAM


def _callbacks(access: MatchBoardAccess) -> set:
    return set(MatchLifecycleHandlers(None, access=access).callbacks())


def test_a_viewer_with_no_capability_is_offered_nothing():
    assert _callbacks(MatchBoardAccess()) == set()


def test_staff_gets_every_callback():
    cb = MatchLifecycleHandlers(None, access=MatchBoardAccess.for_roles(is_staff=True)).callbacks()
    assert set(cb) == set(ALL)
    assert all(callable(fn) for fn in cb.values())


def test_a_tournament_admin_gets_the_same_set_as_staff():
    """Their authority is per tournament, not narrower in kind — the *board* is
    what scopes them (``admin_schedule_page``'s ``tournament_ids``)."""
    assert _callbacks(MatchBoardAccess.for_roles(is_tournament_admin=True)) == set(ALL)


def test_the_proctor_runs_matches_and_amends_nothing():
    """``can_run_match`` admits them; ``can_confirm_match`` deliberately does not."""
    assert _callbacks(MatchBoardAccess.for_roles(is_proctor=True)) == set(RUN)


def test_the_crew_coordinator_is_offered_no_lifecycle_control():
    """The regression this split exists to prevent.

    ``can_approve_crew`` admits them and every other match gate refuses them, so
    a board that hands them Check In / Start / Generate / Stations is a board of
    37 controls that all error. Crew approval is not a callback — it is a slot
    flag — so their callback set is correctly empty.
    """
    assert _callbacks(MatchBoardAccess.for_roles(is_crew_coordinator=True)) == set()


def test_the_stream_manager_is_offered_exactly_the_stage():
    """``assign_stage``'s own docstring names this role; nothing offered it."""
    assert _callbacks(MatchBoardAccess.for_roles(is_stream_manager=True)) == set(STREAM)


def test_an_uncovered_callback_is_omitted_not_none():
    """MatchTableView keys slot registration and event wiring off *presence*."""
    cb = MatchLifecycleHandlers(None, access=MatchBoardAccess(run=True)).callbacks()
    for name in EDIT + CONFIRM + STREAM:
        assert name not in cb


def test_correcting_a_result_does_not_re_finish_the_match():
    """The match is already Finished when the pencil appears.

    Reusing ``on_finish``'s shape would re-run ``finish_match``, rewriting
    ``finished_at`` and re-notifying for a match nobody just played. Recording
    the corrected winner is the whole of the change.
    """
    src = inspect.getsource(MatchLifecycleHandlers.on_edit_result)
    assert "mode='edit'" in src
    # The call, not the word — the handler's docstring explains the omission.
    assert 'finish_match(' not in src
    assert 'confirm_finishing(' not in src


def test_both_surfaces_build_their_view_from_the_shared_handlers():
    for module, fn in ((admin_schedule, admin_schedule.admin_schedule_page),
                       (proctor_station, proctor_station.proctor_station_tab)):
        src = inspect.getsource(fn)
        assert 'MatchLifecycleHandlers(' in src, module.__name__
        assert '**handlers.callbacks()' in src, module.__name__
        assert 'handlers.table_view = table_view' in src, module.__name__


def test_the_proctor_board_declares_only_the_run_capability():
    src = inspect.getsource(proctor_station.proctor_station_tab)
    assert 'MatchBoardAccess(run=True)' in src
    assert 'submit_match_callback' not in src
