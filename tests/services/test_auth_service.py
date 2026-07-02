"""Unit tests for AuthService policy helpers.

These tests stub the model-layer queries (UserRole.filter, Tournament.filter,
user.admin_tournaments.all, etc.) so the policy logic is exercised without
needing a database. The goal is to lock in the role rules so refactors
don't accidentally widen or narrow them.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.services.auth_service import AuthService, get_user_from_discord_id
from models import Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(user_id: int = 1):
    """Build a minimal User stand-in.

    `admin_tournaments` and `crew_coordinated_tournaments` are accessed as
    `await user.<attr>.all().exists()` in the policy code, so they're mocked
    as callables that return an object with an async exists().
    """
    user = SimpleNamespace(id=user_id)
    user.admin_tournaments = SimpleNamespace(
        all=lambda: SimpleNamespace(exists=AsyncMock(return_value=False)),
    )
    user.crew_coordinated_tournaments = SimpleNamespace(
        all=lambda: SimpleNamespace(exists=AsyncMock(return_value=False)),
    )
    return user


def make_match(tournament_id: int = 100, match_id: int = 1):
    return SimpleNamespace(id=match_id, tournament_id=tournament_id)


def make_tournament(tournament_id: int = 100):
    return SimpleNamespace(id=tournament_id)


@pytest.fixture
def patch_roles(monkeypatch):
    """Fixture that lets a test declare what roles a user holds."""

    def _patch(roles_for_user: set[Role] | None = None):
        roles = set(roles_for_user or [])

        class FakeRoleQS:
            def __init__(self, has_match: bool):
                self._has_match = has_match

            async def values_list(self, *_args, **_kwargs):
                return [r.value for r in roles] if self._has_match else []

            async def exists(self):
                return bool(roles) if self._has_match else False

        def fake_filter(*, user=None, role=None, **_kwargs):
            if user is None:
                return FakeRoleQS(False)
            has_match = role is None or role in roles
            return FakeRoleQS(has_match)

        from models import UserRole
        monkeypatch.setattr(UserRole, 'filter', staticmethod(fake_filter))

    return _patch


@pytest.fixture
def patch_tournament_membership(monkeypatch):
    """Mock Tournament.filter so the policy thinks the actor is/isn't TA/CC."""

    def _patch(admin_of: set[int] | None = None, cc_of: set[int] | None = None):
        admin_of = admin_of or set()
        cc_of = cc_of or set()

        class FakeTournamentQS:
            def __init__(self, exists_result):
                self._exists = exists_result

            async def exists(self):
                return self._exists

        def fake_filter(*, id=None, admins__id=None, crew_coordinators__id=None, **_kwargs):
            if admins__id is not None:
                return FakeTournamentQS(id in admin_of)
            if crew_coordinators__id is not None:
                return FakeTournamentQS(id in cc_of)
            return FakeTournamentQS(False)

        from models import Tournament
        monkeypatch.setattr(Tournament, 'filter', staticmethod(fake_filter))

    return _patch


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


class TestPrimitives:
    async def test_none_user_has_no_roles(self, patch_roles):
        patch_roles(set())
        assert await AuthService.is_staff(None) is False
        assert await AuthService.is_proctor(None) is False
        assert await AuthService.is_stream_manager(None) is False

    async def test_is_staff_true_when_user_has_staff_role(self, patch_roles):
        patch_roles({Role.STAFF})
        assert await AuthService.is_staff(make_user()) is True

    async def test_is_staff_false_when_user_has_other_role(self, patch_roles):
        patch_roles({Role.PROCTOR})
        assert await AuthService.is_staff(make_user()) is False

    async def test_get_roles_returns_set_of_role_enums(self, patch_roles):
        patch_roles({Role.PROCTOR, Role.STREAM_MANAGER})
        roles = await AuthService.get_roles(make_user())
        assert roles == {Role.PROCTOR, Role.STREAM_MANAGER}

    async def test_get_roles_empty_for_none_user(self):
        assert await AuthService.get_roles(None) == set()

    async def test_is_tournament_admin_none_user(self):
        assert await AuthService.is_tournament_admin(None, 1) is False

    async def test_is_tournament_admin_true_when_member(self, patch_tournament_membership):
        patch_tournament_membership(admin_of={42})
        assert await AuthService.is_tournament_admin(make_user(), 42) is True

    async def test_is_tournament_admin_false_when_other_tournament(self, patch_tournament_membership):
        patch_tournament_membership(admin_of={42})
        assert await AuthService.is_tournament_admin(make_user(), 99) is False

    async def test_is_crew_coordinator_uses_separate_m2m(self, patch_tournament_membership):
        patch_tournament_membership(admin_of=set(), cc_of={5})
        assert await AuthService.is_crew_coordinator_of(make_user(), 5) is True
        assert await AuthService.is_tournament_admin(make_user(), 5) is False


# ---------------------------------------------------------------------------
# Composite policies — Staff override
# ---------------------------------------------------------------------------


class TestStaffOverride:
    async def test_staff_can_crud_any_match(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.STAFF})
        patch_tournament_membership()
        match = make_match(tournament_id=999)
        assert await AuthService.can_crud_match(make_user(), match) is True

    async def test_staff_can_transition_any_match(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.STAFF})
        patch_tournament_membership()
        assert await AuthService.can_transition_match(make_user(), make_match()) is True

    async def test_staff_can_approve_any_crew(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.STAFF})
        patch_tournament_membership()
        assert await AuthService.can_approve_crew(make_user(), make_match()) is True

    async def test_staff_can_manage_streams(self, patch_roles):
        patch_roles({Role.STAFF})
        assert await AuthService.can_manage_stream_rooms(make_user()) is True

    async def test_staff_can_grant_roles(self, patch_roles):
        patch_roles({Role.STAFF})
        assert await AuthService.can_grant_roles(make_user()) is True

    async def test_staff_can_edit_any_tournament(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.STAFF})
        patch_tournament_membership()
        assert await AuthService.can_edit_tournament(make_user(), make_tournament(123)) is True


# ---------------------------------------------------------------------------
# can_crud_match vs can_transition_match — Proctor distinction
# ---------------------------------------------------------------------------


class TestCrudVsTransition:
    async def test_proctor_can_transition_but_not_crud(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.PROCTOR})
        patch_tournament_membership()  # not TA of anything
        match = make_match()
        assert await AuthService.can_transition_match(make_user(), match) is True
        assert await AuthService.can_crud_match(make_user(), match) is False

    async def test_ta_can_both_for_own_tournament(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership(admin_of={100})
        match = make_match(tournament_id=100)
        assert await AuthService.can_transition_match(make_user(), match) is True
        assert await AuthService.can_crud_match(make_user(), match) is True

    async def test_ta_cannot_crud_other_tournament(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership(admin_of={100})
        match = make_match(tournament_id=200)
        assert await AuthService.can_crud_match(make_user(), match) is False
        assert await AuthService.can_transition_match(make_user(), match) is False

    async def test_regular_user_cannot_transition_or_crud(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership()
        match = make_match()
        assert await AuthService.can_transition_match(make_user(), match) is False
        assert await AuthService.can_crud_match(make_user(), match) is False


# ---------------------------------------------------------------------------
# can_approve_crew — TA OR CC of the match's tournament
# ---------------------------------------------------------------------------


class TestApproveCrew:
    async def test_ta_of_match_tournament_can_approve(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership(admin_of={42})
        match = make_match(tournament_id=42)
        assert await AuthService.can_approve_crew(make_user(), match) is True

    async def test_cc_of_match_tournament_can_approve(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership(admin_of=set(), cc_of={42})
        match = make_match(tournament_id=42)
        assert await AuthService.can_approve_crew(make_user(), match) is True

    async def test_cc_of_other_tournament_cannot_approve(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership(admin_of=set(), cc_of={42})
        match = make_match(tournament_id=99)
        assert await AuthService.can_approve_crew(make_user(), match) is False

    async def test_proctor_alone_cannot_approve_crew(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.PROCTOR})
        patch_tournament_membership()
        assert await AuthService.can_approve_crew(make_user(), make_match()) is False

    async def test_stream_manager_alone_cannot_approve_crew(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.STREAM_MANAGER})
        patch_tournament_membership()
        assert await AuthService.can_approve_crew(make_user(), make_match()) is False


# ---------------------------------------------------------------------------
# can_assign_match_stream — Stream Manager globally OR TA of match's tournament
# ---------------------------------------------------------------------------


class TestAssignMatchStream:
    async def test_stream_manager_can_assign_any_match(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.STREAM_MANAGER})
        patch_tournament_membership()
        match = make_match(tournament_id=999)
        assert await AuthService.can_assign_match_stream(make_user(), match) is True

    async def test_ta_can_assign_own_tournament_match(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership(admin_of={42})
        match = make_match(tournament_id=42)
        assert await AuthService.can_assign_match_stream(make_user(), match) is True

    async def test_ta_cannot_assign_other_tournament_match(self, patch_roles, patch_tournament_membership):
        patch_roles(set())
        patch_tournament_membership(admin_of={42})
        match = make_match(tournament_id=99)
        assert await AuthService.can_assign_match_stream(make_user(), match) is False

    async def test_proctor_alone_cannot_assign_streams(self, patch_roles, patch_tournament_membership):
        patch_roles({Role.PROCTOR})
        patch_tournament_membership()
        assert await AuthService.can_assign_match_stream(make_user(), make_match()) is False


# ---------------------------------------------------------------------------
# can_grant_roles — Staff only
# ---------------------------------------------------------------------------


class TestGrantRoles:
    async def test_non_staff_cannot_grant_roles(self, patch_roles):
        patch_roles({Role.PROCTOR, Role.STREAM_MANAGER})
        assert await AuthService.can_grant_roles(make_user()) is False

    async def test_only_staff_can_grant_roles(self, patch_roles):
        patch_roles({Role.STAFF})
        assert await AuthService.can_grant_roles(make_user()) is True


# ---------------------------------------------------------------------------
# can_submit_triforce_text — paid global role + generator capability
# ---------------------------------------------------------------------------


def make_triforce_tournament(is_active=True, seed_generator='alttpr'):
    return SimpleNamespace(id=1, is_active=is_active, seed_generator=seed_generator)


class TestTriforceSubmit:
    async def test_is_triforce_submitter(self, patch_roles):
        patch_roles({Role.TRIFORCE_SUBMITTER})
        assert await AuthService.is_triforce_submitter(make_user()) is True
        patch_roles({Role.PROCTOR})
        assert await AuthService.is_triforce_submitter(make_user()) is False

    async def test_submitter_can_submit_to_supported_active_tournament(self, patch_roles):
        patch_roles({Role.TRIFORCE_SUBMITTER})
        assert await AuthService.can_submit_triforce_text(
            make_user(), make_triforce_tournament()
        ) is True

    async def test_staff_override_can_submit(self, patch_roles):
        patch_roles({Role.STAFF})
        assert await AuthService.can_submit_triforce_text(
            make_user(), make_triforce_tournament()
        ) is True

    async def test_no_role_cannot_submit(self, patch_roles):
        patch_roles(set())
        assert await AuthService.can_submit_triforce_text(
            make_user(), make_triforce_tournament()
        ) is False

    async def test_unsupported_generator_blocks_submit(self, patch_roles):
        patch_roles({Role.TRIFORCE_SUBMITTER})
        assert await AuthService.can_submit_triforce_text(
            make_user(), make_triforce_tournament(seed_generator='ootr')
        ) is False

    async def test_inactive_tournament_blocks_submit(self, patch_roles):
        patch_roles({Role.TRIFORCE_SUBMITTER})
        assert await AuthService.can_submit_triforce_text(
            make_user(), make_triforce_tournament(is_active=False)
        ) is False


# ---------------------------------------------------------------------------
# ensure() raises PermissionError
# ---------------------------------------------------------------------------


class TestEnsure:
    async def test_ensure_raises_when_disallowed(self):
        with pytest.raises(PermissionError):
            await AuthService.ensure(False, "nope")

    async def test_ensure_silent_when_allowed(self):
        await AuthService.ensure(True)  # should not raise


# ---------------------------------------------------------------------------
# can_view_admin — admin global roles or TA/CC membership (NOT proctor/volunteer)
# ---------------------------------------------------------------------------


def make_ta_user(user_id: int = 1):
    """User whose admin_tournaments.all().exists() resolves True."""
    user = make_user(user_id)
    user.admin_tournaments = SimpleNamespace(
        all=lambda: SimpleNamespace(exists=AsyncMock(return_value=True)),
    )
    return user


class TestViewAdmin:
    async def test_none_user_cannot_view_admin(self):
        assert await AuthService.can_view_admin(None) is False

    async def test_staff_can_view_admin(self, patch_roles):
        patch_roles({Role.STAFF})
        assert await AuthService.can_view_admin(make_user()) is True

    async def test_proctor_alone_cannot_view_admin(self, patch_roles):
        patch_roles({Role.PROCTOR})
        assert await AuthService.can_view_admin(make_user()) is False

    async def test_volunteer_alone_cannot_view_admin(self, patch_roles):
        patch_roles({Role.VOLUNTEER})
        assert await AuthService.can_view_admin(make_user()) is False

    async def test_ta_membership_grants_admin_view(self, patch_roles):
        patch_roles(set())
        assert await AuthService.can_view_admin(make_ta_user()) is True

    async def test_ensure_message_propagates(self):
        with pytest.raises(PermissionError, match="custom message"):
            await AuthService.ensure(False, "custom message")


class TestGetUserFromDiscordId:
    async def test_none_discord_id_returns_none(self):
        assert await get_user_from_discord_id(None) is None

    async def test_active_user_resolved(self, monkeypatch):
        from application.services import auth_service
        user = SimpleNamespace(id=1, is_active=True)
        monkeypatch.setattr(auth_service.User, 'get_or_none', AsyncMock(return_value=user))
        assert await get_user_from_discord_id('123') is user

    async def test_inactive_user_treated_as_logged_out(self, monkeypatch):
        # A deactivated account must resolve to None so it loses page/role access.
        from application.services import auth_service
        user = SimpleNamespace(id=1, is_active=False)
        monkeypatch.setattr(auth_service.User, 'get_or_none', AsyncMock(return_value=user))
        assert await get_user_from_discord_id('123') is None
