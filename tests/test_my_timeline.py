"""The Timeline view's pure rules: lanes for clashes, the 06:00 event day,
which day opens, and the short-name fallback."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from application.services.my_timeline_service import (
    MATCH,
    SHIFT,
    MyTimelineService,
    TimelineItem,
    event_day,
    opening_day,
    place_in_lanes,
)
from models import Tournament

UTC = timezone.utc
T0 = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)


def _item(start_h, hours, kind=MATCH):
    start = T0 + timedelta(hours=start_h)
    return TimelineItem(kind=kind, starts_at=start, ends_at=start + timedelta(hours=hours),
                        title='x', detail='')


def test_separate_items_each_take_the_full_width():
    placed = place_in_lanes([_item(0, 1), _item(2, 1)])
    assert [(p.lane, p.lanes) for p in placed] == [(0, 1), (0, 1)]


def test_a_clash_sits_side_by_side():
    shift = _item(0, 4, SHIFT)
    crew = _item(2.5, 1.5)
    placed = {p.item: (p.lane, p.lanes) for p in place_in_lanes([crew, shift])}
    assert placed[shift] == (0, 2)
    assert placed[crew] == (1, 2)


def test_back_to_back_items_do_not_clash():
    placed = place_in_lanes([_item(0, 1), _item(1, 1)])
    assert all(p.lanes == 1 for p in placed)


def test_a_late_night_match_belongs_to_the_evening_before():
    one_am = datetime(2026, 10, 24, 1, 0, tzinfo=UTC)
    assert event_day(one_am, 'UTC') == date(2026, 10, 23)
    assert event_day(one_am + timedelta(hours=6), 'UTC') == date(2026, 10, 24)


def test_opening_day_prefers_today_then_the_next_day_on():
    days = [date(2026, 10, 22), date(2026, 10, 24)]
    assert opening_day(days, date(2026, 10, 22)) == date(2026, 10, 22)
    assert opening_day(days, date(2026, 10, 23)) == date(2026, 10, 24)
    assert opening_day(days, date(2026, 10, 30)) == date(2026, 10, 24)
    assert opening_day([], date(2026, 10, 23)) is None


def _match(players, tournament):
    return SimpleNamespace(
        id=7, title='', scheduled_at=T0, tournament=tournament,
        players=[SimpleNamespace(user_id=u.id, user=u) for u in players],
    )


def test_a_played_match_names_the_opponent_and_the_short_name():
    me = SimpleNamespace(id=1, preferred_name='Me')
    them = SimpleNamespace(id=2, preferred_name='Them')
    tournament = Tournament(name='A Link to the Past Main', short_name='ALTTPR', average_match_duration=60)
    item = MyTimelineService._match_item(_match([me, them], tournament), me, None)
    assert (item.kind, item.title, item.detail) == (MATCH, 'vs Them', 'ALTTPR')
    assert item.ends_at - item.starts_at == timedelta(minutes=60)


def test_a_crewed_match_says_the_role_and_who_plays():
    me = SimpleNamespace(id=1, preferred_name='Me')
    a = SimpleNamespace(id=2, preferred_name='A')
    b = SimpleNamespace(id=3, preferred_name='B')
    tournament = Tournament(name='Super Metroid', short_name=None)
    item = MyTimelineService._match_item(_match([a, b], tournament), me, 'commentator')
    assert (item.title, item.detail) == ('Commentary', 'A vs B · Super Metroid')
    assert item.ends_at - item.starts_at == timedelta(minutes=90)


def test_short_label_falls_back_to_the_name():
    assert Tournament(name='Full', short_name='  ').short_label == 'Full'
    assert Tournament(name='Full', short_name='F').short_label == 'F'
