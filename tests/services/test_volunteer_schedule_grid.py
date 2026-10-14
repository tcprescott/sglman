"""Volunteer → Full Schedule: the day grid's layout rules (no DB)."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from application.services.volunteer.volunteer_schedule_grid import (
    GridRole,
    apply_roles,
    arrange_roles,
    build_day_grid,
    day_window,
    roles_config,
)
from pages.volunteer_tabs.full_schedule import day_label, is_customized, names_that_fit, opening_day

MIDNIGHT = datetime(2026, 10, 23, 4, 0, tzinfo=timezone.utc)


def _at(hour: float) -> datetime:
    return MIDNIGHT + timedelta(hours=hour)


def _assignment(user_id: int, name: str, draft: bool = False):
    return SimpleNamespace(
        user_id=user_id, user=SimpleNamespace(preferred_name=name), auto_generated=draft,
    )


def _shift(position_id: int, position: str, start: float, end: float, people=(), slots=1):
    return SimpleNamespace(
        position_id=position_id, position=SimpleNamespace(name=position),
        starts_at=_at(start), ends_at=_at(end), label='', slots_needed=slots,
        assignments=list(people),
    )


def test_one_column_per_position_in_arrival_order():
    grid = build_day_grid([
        _shift(2, 'Admin Desk', 8, 10, [_assignment(1, 'dani')]),
        _shift(2, 'Admin Desk', 10, 12, [_assignment(2, 'jamevil')]),
        _shift(5, 'Race Proctor', 12, 16, [_assignment(3, 'lumaga')]),
    ], MIDNIGHT, viewer_id=None)

    assert [c.position for c in grid.columns] == ['Admin Desk', 'Race Proctor']
    assert [len(c.shifts) for c in grid.columns] == [2, 1]
    assert (grid.first_hour, grid.last_hour) == (8, 16)


def test_drafts_are_left_out_and_counted_as_open():
    grid = build_day_grid([
        _shift(1, 'Check In', 8, 12, [_assignment(1, 'told'), _assignment(2, 'drafted', draft=True)], slots=2),
    ], MIDNIGHT, viewer_id=None)

    shift = grid.columns[0].shifts[0]
    assert [p.name for p in shift.people] == ['told']
    assert shift.open_slots == 1


def test_the_viewers_shift_is_marked():
    grid = build_day_grid([
        _shift(1, 'Admin Desk', 20, 22, [_assignment(7, 'Synack'), _assignment(8, 'other')], slots=2),
    ], MIDNIGHT, viewer_id=7)

    shift = grid.columns[0].shifts[0]
    assert shift.has_viewer
    assert [p.is_viewer for p in shift.people] == [False, True]


def test_late_shifts_stay_on_the_evening_they_start_and_are_clipped_to_the_day():
    start, end = day_window(MIDNIGHT)
    assert (start, end) == (_at(6), _at(30))

    grid = build_day_grid([
        _shift(1, 'Board Game Room', 20, 26),
        _shift(1, 'Board Game Room', 28, 34),
    ], MIDNIGHT, viewer_id=None)

    shifts = grid.columns[0].shifts
    assert (shifts[0].start_hour, shifts[0].end_hour) == (20, 26)
    assert (shifts[1].start_hour, shifts[1].end_hour) == (28, 30)
    assert grid.last_hour == 30


def test_an_empty_day_has_no_columns():
    grid = build_day_grid([], MIDNIGHT, viewer_id=None)
    assert grid.columns == ()
    assert list(grid.hours) == []


def test_now_falls_on_the_grid_only_inside_its_hours():
    grid = build_day_grid([_shift(1, 'Check In', 8, 12)], MIDNIGHT, viewer_id=None)
    assert grid.hour_at(_at(9.5)) == 9.5
    assert grid.hour_at(_at(13)) is None


def test_a_crowded_block_keeps_a_line_for_more():
    crowd = [_assignment(i, f'v{i}') for i in range(10)]
    grid = build_day_grid([_shift(1, 'Setup', 8, 12, crowd, slots=16)], MIDNIGHT, viewer_id=None)
    shift = grid.columns[0].shifts[0]
    shown = names_that_fit(shift)
    assert 0 < shown < 10

    pair = build_day_grid([_shift(1, 'Tech', 8, 10, crowd[:2], slots=2)], MIDNIGHT, viewer_id=None)
    assert names_that_fit(pair.columns[0].shifts[0]) == 2


def test_opening_day_prefers_the_remembered_day_then_today():
    days = [date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]
    assert opening_day(days, '2026-10-21', date(2026, 10, 22)) == days[0]
    assert opening_day(days, '2025-01-01', date(2026, 10, 22)) == days[1]
    assert opening_day(days, None, date(2026, 11, 1)) == days[0]
    assert opening_day([], None, date(2026, 11, 1)) is None


def test_day_label():
    assert day_label(date(2026, 10, 23)) == 'Fri 23'


def test_overlapping_shifts_of_one_position_sit_side_by_side():
    grid = build_day_grid([
        _shift(1, 'Broadcast Tech', 8, 12),
        _shift(1, 'Broadcast Tech', 10, 14),
        _shift(1, 'Broadcast Tech', 12, 16),
        _shift(1, 'Broadcast Tech', 18, 20),
    ], MIDNIGHT, viewer_id=None)

    placed = [(s.start_hour, s.lane, s.lanes) for s in grid.columns[0].shifts]
    assert placed == [(8, 0, 2), (10, 1, 2), (12, 0, 2), (18, 0, 1)]


POSITIONS = [(1, 'Admin Desk'), (2, 'Check In'), (3, 'Race Proctor')]


def test_roles_follow_the_saved_order_and_new_roles_go_last_and_shown():
    saved = [{'name': '3', 'visible': True}, {'name': '2', 'visible': False}, {'name': '99'}, {'name': 'x'}]
    roles = arrange_roles(POSITIONS + [(4, 'Board Game Room')], saved)

    assert [(r.position_id, r.visible) for r in roles] == [(3, True), (2, False), (1, True), (4, True)]


def test_no_saved_choice_is_every_role_in_the_communitys_order():
    roles = arrange_roles(POSITIONS, None)
    assert [r.name for r in roles] == ['Admin Desk', 'Check In', 'Race Proctor']
    assert not is_customized(roles, POSITIONS)
    assert is_customized(roles[::-1], POSITIONS)


def test_hidden_roles_drop_out_and_the_rest_take_the_viewers_order():
    grid = build_day_grid([
        _shift(1, 'Admin Desk', 8, 10),
        _shift(2, 'Check In', 7, 9),
        _shift(3, 'Race Proctor', 12, 22),
        _shift(9, 'Retired Role', 12, 13),
    ], MIDNIGHT, viewer_id=None)
    roles = (GridRole(3, 'Race Proctor'), GridRole(1, 'Admin Desk'), GridRole(2, 'Check In', visible=False))

    shown = apply_roles(grid, roles)

    assert [c.position for c in shown.columns] == ['Race Proctor', 'Admin Desk', 'Retired Role']
    assert (shown.first_hour, shown.last_hour) == (8, 22)


def test_saving_keeps_another_communitys_choices():
    roles = (GridRole(2, 'Check In', visible=False), GridRole(1, 'Admin Desk'))
    saved = [{'name': '1', 'visible': True}, {'name': '500', 'visible': False}]

    config = roles_config(roles, saved, limit=64)

    assert config == [
        {'name': '2', 'visible': False, 'width': None},
        {'name': '1', 'visible': True, 'width': None},
        {'name': '500', 'visible': False, 'width': None},
    ]
    assert len(roles_config(roles, saved, limit=2)) == 2
