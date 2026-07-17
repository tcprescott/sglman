from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.crew_service import CrewService


pytestmark = pytest.mark.usefixtures("bypass_auth")
@pytest.fixture(autouse=True)
def bypass_transactions(monkeypatch):
    """Replace in_transaction() with a no-op async context manager for unit tests."""
    @asynccontextmanager
    async def noop_tx(*_args, **_kwargs):
        yield None

    monkeypatch.setattr('application.services.crew_service.in_transaction', noop_tx)


@pytest.fixture
def service():
    svc = object.__new__(CrewService)
    svc.commentator_repository = MagicMock()
    svc.commentator_repository.acknowledge = AsyncMock(side_effect=lambda c: c)
    svc.commentator_repository.get_by_id = AsyncMock()
    svc.tracker_repository = MagicMock()
    svc.tracker_repository.acknowledge = AsyncMock(side_effect=lambda c: c)
    svc.tracker_repository.get_by_id = AsyncMock()
    svc.match_repository = MagicMock()
    svc.match_repository.get_by_id = AsyncMock()
    svc.match_repository.get_players = AsyncMock(return_value=[])
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    svc.discord_service = MagicMock()
    svc.discord_service.send_dm_with_crew_acknowledgment_button = AsyncMock(
        return_value=(True, 'sent')
    )
    return svc


def make_signup_match(**overrides):
    """A lightweight match stand-in for crew signup/undo tests."""
    defaults = dict(
        id=1,
        finished_at=None,
        commentators=[],
        trackers=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_user(user_id=1, discord_id='12345'):
    user = MagicMock()
    user.id = user_id
    user.discord_id = discord_id
    user.preferred_name = 'Alice'
    return user


def make_match(match_id=42):
    match = MagicMock()
    match.id = match_id
    # Keep the DM message builder on a simple path: no title/schedule/stream room.
    match.title = None
    match.scheduled_at = None
    match.stream_room = None
    match.players.all.return_value.prefetch_related = AsyncMock(return_value=[])
    return match


def make_crew(*, user, match, approved=True, acknowledged_at=None, crew_id=7):
    crew = MagicMock()
    crew.id = crew_id
    crew.user = user
    crew.user_id = user.id
    crew.match = match
    crew.match_id = match.id
    crew.approved = approved
    crew.acknowledged_at = acknowledged_at
    crew.fetch_related = AsyncMock()
    crew.refresh_from_db = AsyncMock()
    crew.save = AsyncMock()
    return crew


class TestAcknowledgeCrewAssignment:
    async def test_commentator_happy_path(self, service):
        user = make_user()
        match = make_match()
        crew = make_crew(user=user, match=match)
        service.commentator_repository.get_by_id.return_value = crew

        result = await service.acknowledge_crew_assignment(crew.id, 'commentator', user)

        assert result is crew
        service.commentator_repository.acknowledge.assert_awaited_once_with(crew)
        service.audit_service.write_log.assert_awaited_once()
        action_arg = service.audit_service.write_log.await_args.args[1]
        assert action_arg == 'crew.acknowledged'

    async def test_tracker_happy_path(self, service):
        user = make_user()
        match = make_match()
        crew = make_crew(user=user, match=match)
        service.tracker_repository.get_by_id.return_value = crew

        await service.acknowledge_crew_assignment(crew.id, 'tracker', user)

        service.tracker_repository.acknowledge.assert_awaited_once_with(crew)

    async def test_rejects_when_not_approved(self, service):
        user = make_user()
        crew = make_crew(user=user, match=make_match(), approved=False)
        service.commentator_repository.get_by_id.return_value = crew

        with pytest.raises(ValueError, match='not been approved'):
            await service.acknowledge_crew_assignment(crew.id, 'commentator', user)

        service.commentator_repository.acknowledge.assert_not_called()

    async def test_already_acknowledged_is_idempotent_noop(self, service):
        user = make_user()
        crew = make_crew(
            user=user, match=make_match(),
            approved=True, acknowledged_at=datetime.now(),
        )
        service.commentator_repository.get_by_id.return_value = crew

        result = await service.acknowledge_crew_assignment(crew.id, 'commentator', user)

        assert result is crew
        service.commentator_repository.acknowledge.assert_not_called()
        service.audit_service.write_log.assert_not_called()

    async def test_rejects_when_user_mismatch(self, service):
        other_user = make_user(user_id=99)
        crew = make_crew(user=make_user(user_id=1), match=make_match())
        service.commentator_repository.get_by_id.return_value = crew

        with pytest.raises(ValueError, match='only acknowledge your own'):
            await service.acknowledge_crew_assignment(crew.id, 'commentator', other_user)

    async def test_rejects_when_crew_missing(self, service):
        service.commentator_repository.get_by_id.return_value = None
        with pytest.raises(ValueError, match='not found'):
            await service.acknowledge_crew_assignment(123, 'commentator', make_user())


class TestUpdateCrewApproval:
    async def test_approve_triggers_dm(self, service):
        user = make_user()
        match = make_match()
        crew = make_crew(user=user, match=match, approved=False)

        await service.update_crew_approval(crew, 'commentator', approved=True, actor=user)

        assert crew.approved is True
        crew.save.assert_awaited_once()
        # The DM is built and enqueued (awaited later by the queue worker).
        service.discord_service.send_dm_with_crew_acknowledgment_button.assert_called_once()
        kwargs_or_args = service.discord_service.send_dm_with_crew_acknowledgment_button.call_args.args
        assert kwargs_or_args[2] == 'commentator'
        assert kwargs_or_args[3] == crew.id

    async def test_unapprove_clears_acknowledgment_and_audits_previously_acknowledged(self, service):
        user = make_user()
        crew = make_crew(
            user=user, match=make_match(),
            approved=True, acknowledged_at=datetime.now(),
        )

        await service.update_crew_approval(crew, 'commentator', approved=False, actor=user)

        assert crew.approved is False
        assert crew.acknowledged_at is None
        service.discord_service.send_dm_with_crew_acknowledgment_button.assert_not_called()
        details = service.audit_service.write_log.await_args.args[2]
        assert details['approved'] is False
        assert details['previously_acknowledged'] is True

    async def test_idempotent_when_state_unchanged(self, service):
        user = make_user()
        crew = make_crew(user=user, match=make_match(), approved=True)

        await service.update_crew_approval(crew, 'commentator', approved=True, actor=user)

        service.discord_service.send_dm_with_crew_acknowledgment_button.assert_not_called()
        service.audit_service.write_log.assert_not_called()
        crew.save.assert_not_called()

    async def test_dm_failure_does_not_raise(self, service):
        user = make_user()
        crew = make_crew(user=user, match=make_match(), approved=False)
        service.discord_service.send_dm_with_crew_acknowledgment_button = AsyncMock(
            side_effect=RuntimeError('discord boom')
        )

        # Should complete without raising; approval and audit still happen.
        await service.update_crew_approval(crew, 'commentator', approved=True, actor=user)

        assert crew.approved is True
        service.audit_service.write_log.assert_awaited_once()


# ---------------------------------------------------------------------------
# signup_crew
# ---------------------------------------------------------------------------


class TestSignupCrew:
    async def test_raises_for_invalid_role(self, service):
        with pytest.raises(ValueError, match="Invalid role"):
            await service.signup_crew(match_id=1, user=MagicMock(), role="referee")

    async def test_raises_when_match_not_found(self, service):
        service.match_repository.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await service.signup_crew(match_id=999, user=MagicMock(), role="commentator")

    async def test_raises_when_match_finished(self, service):
        match = make_signup_match(finished_at=datetime(2025, 1, 16, 20, 0))
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="already finished"):
            await service.signup_crew(match_id=1, user=SimpleNamespace(id=42), role="commentator")

    async def test_raises_when_commentator_already_signed_up(self, service):
        user = SimpleNamespace(id=42)
        match = make_signup_match(commentators=[SimpleNamespace(user_id=42)])
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="already signed up"):
            await service.signup_crew(match_id=1, user=user, role="commentator")

    async def test_raises_when_tracker_already_signed_up(self, service):
        user = SimpleNamespace(id=42)
        match = make_signup_match(trackers=[SimpleNamespace(user_id=42)])
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="already signed up"):
            await service.signup_crew(match_id=1, user=user, role="tracker")

    async def test_creates_commentator_when_valid(self, service):
        user = SimpleNamespace(id=99)
        match = make_signup_match(commentators=[])
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        service.commentator_repository.create = AsyncMock()
        await service.signup_crew(match_id=1, user=user, role="commentator")
        service.commentator_repository.create.assert_awaited_once_with(
            match=match, user=user, approved=False
        )

    async def test_creates_tracker_when_valid(self, service):
        user = SimpleNamespace(id=99)
        match = make_signup_match(trackers=[])
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        service.tracker_repository.create = AsyncMock()
        await service.signup_crew(match_id=1, user=user, role="tracker")
        service.tracker_repository.create.assert_awaited_once_with(
            match=match, user=user, approved=False
        )

    async def test_invalid_role_check_precedes_db_lookup(self, service):
        service.match_repository.get_by_id = AsyncMock()
        with pytest.raises(ValueError, match="Invalid role"):
            await service.signup_crew(match_id=1, user=MagicMock(), role="judge")
        service.match_repository.get_by_id.assert_not_awaited()

    async def test_raises_when_user_is_a_player(self, service):
        user = SimpleNamespace(id=42)
        match = make_signup_match()
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        service.match_repository.get_players = AsyncMock(return_value=[SimpleNamespace(user_id=42)])
        with pytest.raises(ValueError, match="[Pp]layer"):
            await service.signup_crew(match_id=1, user=user, role="commentator")


# ---------------------------------------------------------------------------
# undo_crew_signup
# ---------------------------------------------------------------------------


class TestUndoCrewSignup:
    async def test_raises_for_invalid_role(self, service):
        with pytest.raises(ValueError, match="Invalid role"):
            await service.undo_crew_signup(match_id=1, user=MagicMock(), role="referee")

    async def test_raises_when_match_not_found(self, service):
        service.match_repository.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await service.undo_crew_signup(match_id=999, user=MagicMock(), role="commentator")

    async def test_raises_when_commentator_not_signed_up(self, service):
        user = SimpleNamespace(id=42)
        match = make_signup_match(commentators=[])
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="not signed up"):
            await service.undo_crew_signup(match_id=1, user=user, role="commentator")

    async def test_raises_when_tracker_not_signed_up(self, service):
        user = SimpleNamespace(id=42)
        match = make_signup_match(trackers=[])
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="not signed up"):
            await service.undo_crew_signup(match_id=1, user=user, role="tracker")

    async def test_deletes_commentator_when_found(self, service):
        user = SimpleNamespace(id=42)
        crew_member = SimpleNamespace(user_id=42, delete=AsyncMock())
        match = make_signup_match(commentators=[crew_member])
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        await service.undo_crew_signup(match_id=1, user=user, role="commentator")
        crew_member.delete.assert_awaited_once()

    async def test_deletes_tracker_when_found(self, service):
        user = SimpleNamespace(id=42)
        crew_member = SimpleNamespace(user_id=42, delete=AsyncMock())
        match = make_signup_match(trackers=[crew_member])
        service.match_repository.get_by_id = AsyncMock(return_value=match)
        await service.undo_crew_signup(match_id=1, user=user, role="tracker")
        crew_member.delete.assert_awaited_once()

    async def test_invalid_role_check_precedes_db_lookup(self, service):
        service.match_repository.get_by_id = AsyncMock()
        with pytest.raises(ValueError, match="Invalid role"):
            await service.undo_crew_signup(match_id=1, user=MagicMock(), role="judge")
        service.match_repository.get_by_id.assert_not_awaited()
