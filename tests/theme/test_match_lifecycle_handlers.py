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
from contextlib import nullcontext
from types import SimpleNamespace

import pages.admin_tabs.admin_schedule as admin_schedule
import pages.volunteer_tabs.proctor_station as proctor_station
import theme.tables.match_lifecycle as match_lifecycle
from theme.tables.match_access import MatchBoardAccess
from theme.tables.match_lifecycle import MatchLifecycleHandlers

RUN = ['on_generate_seed', 'on_seat', 'on_start', 'on_finish', 'on_assign_stations']
EDIT = ['on_edit']
CONFIRM = ['on_confirm', 'on_edit_result']
STREAM = ['on_set_stage']
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


# --- The Stage select: one control for two different fields -----------------

class _Recorder:
    """Stands in for ``MatchService``, recording what the handler asked for."""

    def __init__(self):
        self.stages = []
        self.candidates = []

    async def assign_stage(self, match_id, stream_room_id, actor=None):
        self.stages.append((match_id, stream_room_id))

    async def set_stream_candidate(self, match_id, flag, actor=None):
        self.candidates.append((match_id, flag))


class _Rows:
    def __init__(self):
        self.refreshed = []

    async def update_row_by_id(self, match_id, flash=False):
        self.refreshed.append(match_id)


def _stage_handlers(monkeypatch, *, stream_room_id=None, is_stream_candidate=False):
    """Handlers whose one match is in the given stage/candidate state."""
    row = SimpleNamespace(
        id=7, stream_room_id=stream_room_id, is_stream_candidate=is_stream_candidate,
    )

    class _Model:
        @staticmethod
        async def get(**_kwargs):
            return row

    monkeypatch.setattr(match_lifecycle, 'Match', _Model)
    monkeypatch.setattr(match_lifecycle, 'require_tenant_id', lambda: 1)
    # ``notify_error`` reaches for a NiceGUI client, which no unit test has.
    notified = []
    monkeypatch.setattr(match_lifecycle, 'notify_error', notified.append)

    handlers = MatchLifecycleHandlers(
        nullcontext(), access=MatchBoardAccess.for_roles(is_staff=True),
    )
    handlers.match_service = _Recorder()
    handlers.table_view = _Rows()

    async def _actor():
        return None
    handlers._actor = _actor
    handlers.notified = notified
    return handlers


async def test_picking_a_stage_assigns_it_and_leaves_the_flag_alone(monkeypatch):
    """A staged match still counts as a candidate in the coverage reports.

    The cell stops *showing* candidate because the stage is the more specific
    answer; clearing the flag here would drop the match out of the one report
    that asks whether its crew is covered.
    """
    handlers = _stage_handlers(monkeypatch, is_stream_candidate=True)
    await handlers.on_set_stage(7, 3)
    assert handlers.match_service.stages == [(7, 3)]
    assert handlers.match_service.candidates == []


async def test_picking_candidate_flags_the_match_and_takes_it_off_its_stage(monkeypatch):
    """``Candidate`` is the answer *before* a stage is picked, so it cannot keep one."""
    handlers = _stage_handlers(monkeypatch, stream_room_id=3)
    await handlers.on_set_stage(7, 'candidate')
    assert handlers.match_service.stages == [(7, None)]
    assert handlers.match_service.candidates == [(7, True)]


async def test_clearing_the_select_clears_both_the_stage_and_the_flag(monkeypatch):
    handlers = _stage_handlers(monkeypatch, stream_room_id=3, is_stream_candidate=True)
    await handlers.on_set_stage(7, None)
    assert handlers.match_service.stages == [(7, None)]
    assert handlers.match_service.candidates == [(7, False)]


async def test_re_picking_what_is_already_set_writes_nothing(monkeypatch):
    """Every write audits, publishes an event and can DM — a no-op must not.

    A ``q-select`` re-emits on reselection, and the row refresh after a failed
    write reselects the stored value.
    """
    handlers = _stage_handlers(monkeypatch, stream_room_id=3)
    await handlers.on_set_stage(7, 3)
    assert handlers.match_service.stages == []
    assert handlers.match_service.candidates == []


async def test_a_refused_write_still_refreshes_the_row(monkeypatch):
    """The select is driven by the row, so the refusal has to snap it back."""
    handlers = _stage_handlers(monkeypatch)

    async def refuse(*_args, **_kwargs):
        raise PermissionError('nope')
    handlers.match_service.assign_stage = refuse

    await handlers.on_set_stage(7, 3)
    assert handlers.table_view.refreshed == [7]
    assert [str(e) for e in handlers.notified] == ['nope']
