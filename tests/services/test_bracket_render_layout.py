"""Integration check: the bracket layout walker vs. real engine-generated graphs.

The pure walker unit tests (tests/theme/test_bracket_layout.py) use hand-built
trees; this drives the actual ``BracketService`` (byes, the irregular double-elim
losers bracket, the grand final + reset) and asserts the walker places every
match exactly once in its section with no in-column overlap, centers parents on
their feeders, and numbers matches uniquely. It lives under tests/services (it
exercises the service) — the walker under test is theme/brackets/layout.py.
"""

import pytest

from application.services.bracket_service import BracketService
from models import BracketFormat, Role, Tournament, User, UserRole
from theme.brackets.layout import (
    CARD_HEIGHT,
    MatchNode,
    assign_match_numbers,
    layout_section,
)

pytestmark = pytest.mark.usefixtures("db")


async def _staff() -> User:
    user = await User.create(discord_id=1234, username='staff')
    await UserRole.create(user=user, role=Role.STAFF)
    return user


async def _started(service, fmt, n, config=None):
    actor = await _staff()
    t = await Tournament.create(name='Cup')
    bracket = await service.create_bracket(actor, t.id, 'Main', fmt, config=config)
    for i in range(1, n + 1):
        entrant = await service.add_entrant(actor, t.id, f'P{i}')
        await service.enroll(actor, bracket.id, entrant.id, seed=i)
    await service.start_bracket(actor, bracket.id)
    return actor, bracket


def _nodes(matches):
    return [
        MatchNode(id=m.id, round=m.round, position=m.position, winner_to_id=m.winner_to_id)
        for m in matches
    ]


def _assert_no_overlap(layout):
    by_col = {}
    for p in layout.placements.values():
        by_col.setdefault(p.col, []).append(p)
    for placements in by_col.values():
        ordered = sorted(placements, key=lambda p: p.top)
        for a, b in zip(ordered, ordered[1:]):
            assert a.top + CARD_HEIGHT <= b.top + 1e-9


@pytest.mark.parametrize(
    "fmt,n",
    [
        (BracketFormat.SINGLE_ELIM, 4),
        (BracketFormat.SINGLE_ELIM, 6),   # byes (non power of two)
        (BracketFormat.SINGLE_ELIM, 8),
        (BracketFormat.SINGLE_ELIM, 16),
        (BracketFormat.DOUBLE_ELIM, 4),
        (BracketFormat.DOUBLE_ELIM, 8),
        (BracketFormat.DOUBLE_ELIM, 5),   # byes + losers feed-ins
    ],
)
async def test_every_match_placed_without_overlap(fmt, n):
    service = BracketService()
    _, bracket = await _started(service, fmt, n)
    matches = await service.list_matches(bracket.id)

    positive = [m for m in matches if m.round > 0]
    negative = [m for m in matches if m.round < 0]
    winners = layout_section(_nodes(positive))
    losers = layout_section(_nodes(negative))

    placed = set(winners.placements) | set(losers.placements)
    assert placed == {m.id for m in matches}

    _assert_no_overlap(winners)
    _assert_no_overlap(losers)

    # Parents sit vertically between their in-section winner-feeders.
    for section, ms in ((winners, positive), (losers, negative)):
        section_ids = {m.id for m in ms}
        children = {}
        for m in ms:
            if m.winner_to_id in section_ids:
                children.setdefault(m.winner_to_id, []).append(m.id)
        for parent_id, kids in children.items():
            centers = [section.placements[k].center_y for k in kids]
            assert (
                min(centers) - 1e-9
                <= section.placements[parent_id].center_y
                <= max(centers) + 1e-9
            )


async def test_match_numbers_unique_and_complete():
    service = BracketService()
    _, bracket = await _started(service, BracketFormat.DOUBLE_ELIM, 8)
    matches = await service.list_matches(bracket.id)
    nums = assign_match_numbers(_nodes(matches))
    assert set(nums) == {m.id for m in matches}
    assert len(set(nums.values())) == len(matches)
    assert min(nums.values()) == 1
    assert max(nums.values()) == len(matches)
