"""``MatchBoardAccess`` must agree with the gates the services actually apply.

The board's job is to offer only what the service will accept. Every finding
this class exists to close was a disagreement between the two, so these tests
assert the pairing directly: for each role, the capability the board grants and
the ``AuthService`` predicate that decides the same question must match.

They are pure-Python — the ``AuthService`` half runs against stand-ins rather
than a database — because the point is the *policy*, not the query.
"""

from types import SimpleNamespace

import pytest

from application.services import AuthService
from models import Role
from theme.tables.match_access import MatchBoardAccess

# (field on MatchBoardAccess, the AuthService gate that decides the same thing)
PAIRS = [
    ('edit', AuthService.can_crud_match),
    ('run', AuthService.can_run_match),
    ('confirm', AuthService.can_confirm_match),
    ('assign_stream', AuthService.can_assign_match_stream),
    ('approve_crew', AuthService.can_approve_crew),
]

# Each role as the board resolves it, and as the services see it.
ROLES = {
    'staff': (dict(is_staff=True), {Role.STAFF}, False, False),
    'proctor': (dict(is_proctor=True), {Role.PROCTOR}, False, False),
    'tournament_admin': (dict(is_tournament_admin=True), set(), True, False),
    'stream_manager': (dict(is_stream_manager=True), {Role.STREAM_MANAGER}, False, False),
    'crew_coordinator': (dict(is_crew_coordinator=True), set(), False, True),
}


@pytest.fixture
def patch_gates(monkeypatch):
    """Point the ``AuthService`` role lookups at a fixed set of grants."""
    def apply(roles: set, is_ta: bool, is_cc: bool):
        # ``has_role`` is the one leaf every role predicate bottoms out in, so
        # patching it (rather than each ``is_*``) keeps the real ``is_staff`` /
        # ``is_proctor`` / ``is_stream_manager`` bodies under test.
        async def has_role(_user, role):
            return role in roles

        async def get_roles(_user):
            return roles

        async def is_super_admin(_user):
            return False

        async def is_tournament_admin(_user, _tid):
            return is_ta

        async def is_crew_coordinator_of(_user, _tid):
            return is_cc

        monkeypatch.setattr(AuthService, 'has_role', staticmethod(has_role))
        monkeypatch.setattr(AuthService, 'get_roles', staticmethod(get_roles))
        monkeypatch.setattr(AuthService, 'is_super_admin', staticmethod(is_super_admin))
        monkeypatch.setattr(AuthService, 'is_tournament_admin', staticmethod(is_tournament_admin))
        monkeypatch.setattr(AuthService, 'is_crew_coordinator_of', staticmethod(is_crew_coordinator_of))
    return apply


@pytest.mark.parametrize('role', list(ROLES))
@pytest.mark.parametrize('field,gate', PAIRS)
async def test_every_capability_matches_the_service_gate(role, field, gate, patch_gates):
    kwargs, roles, is_ta, is_cc = ROLES[role]
    patch_gates(roles, is_ta, is_cc)

    board = getattr(MatchBoardAccess.for_roles(**kwargs), field)
    service = await gate(SimpleNamespace(id=1), SimpleNamespace(id=1, tournament_id=100))

    assert board is service, (
        f'{role}: the board says {field}={board} and {gate.__name__} says {service}'
    )


def test_a_default_board_offers_nothing():
    access = MatchBoardAccess()
    assert not access.any()
    assert not any(getattr(access, f) for f, _gate in PAIRS)


def test_staff_gets_every_capability():
    assert all(getattr(MatchBoardAccess.for_roles(is_staff=True), f) for f, _ in PAIRS)


def test_a_crew_coordinator_gets_exactly_one():
    access = MatchBoardAccess.for_roles(is_crew_coordinator=True)
    assert [f for f, _ in PAIRS if getattr(access, f)] == ['approve_crew']


def test_a_stream_manager_gets_exactly_one():
    access = MatchBoardAccess.for_roles(is_stream_manager=True)
    assert [f for f, _ in PAIRS if getattr(access, f)] == ['assign_stream']


def test_a_proctor_runs_matches_and_nothing_else():
    access = MatchBoardAccess.for_roles(is_proctor=True)
    assert [f for f, _ in PAIRS if getattr(access, f)] == ['run']


def test_capabilities_combine_rather_than_replace():
    """One person can hold two roles; the board must be their union."""
    access = MatchBoardAccess.for_roles(is_stream_manager=True, is_crew_coordinator=True)
    assert access.assign_stream and access.approve_crew
    assert not access.edit and not access.run and not access.confirm
