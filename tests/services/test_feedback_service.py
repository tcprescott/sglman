from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.audit_service import AuditActions
from application.services.feedback_service import FeedbackService
from models import Feedback, FeedbackCategory, FeedbackStatus, User


@pytest.fixture
def service():
    """A FeedbackService with mocked repository + audit for fast unit tests."""
    svc = object.__new__(FeedbackService)
    svc.repository = MagicMock()
    svc.repository.create = AsyncMock(side_effect=lambda **kwargs: _fake_feedback(**kwargs))
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


def _fake_feedback(**kwargs):
    fb = MagicMock()
    fb.id = 1
    for key, value in kwargs.items():
        setattr(fb, key, value)
    return fb


class TestSubmit:
    async def test_happy_path_creates_and_audits(self, service):
        actor = MagicMock(spec=User)
        feedback = await service.submit(
            actor=actor,
            category='bug',
            message='  something is broken  ',
            page_url='/admin/users',
        )

        service.repository.create.assert_awaited_once()
        kwargs = service.repository.create.await_args.kwargs
        assert kwargs['user'] is actor
        assert kwargs['category'] == FeedbackCategory.BUG
        assert kwargs['message'] == 'something is broken'  # trimmed
        assert kwargs['page_url'] == '/admin/users'

        service.audit_service.write_log.assert_awaited_once()
        args = service.audit_service.write_log.await_args.args
        assert args[0] is actor
        assert args[1] == AuditActions.FEEDBACK_SUBMITTED
        assert feedback.id == 1

    async def test_empty_message_raises(self, service):
        with pytest.raises(ValueError):
            await service.submit(actor=MagicMock(), category='bug', message='   ', page_url='/')
        service.repository.create.assert_not_awaited()

    async def test_unknown_category_coerces_to_other(self, service):
        await service.submit(actor=MagicMock(), category='nonsense', message='hi', page_url='/')
        assert service.repository.create.await_args.kwargs['category'] == FeedbackCategory.OTHER

    async def test_page_url_truncated_to_column_length(self, service):
        await service.submit(
            actor=MagicMock(), category='other', message='hi', page_url='/x' * 600,
        )
        assert len(service.repository.create.await_args.kwargs['page_url']) == 512


class TestSubmitWithDb:
    async def test_persists_to_database(self, db):
        actor = await User.create(discord_id=555, username='attendee')
        feedback = await FeedbackService().submit(
            actor=actor,
            category='praise',
            message='great event!',
            page_url='/volunteer',
        )

        stored = await Feedback.get(id=feedback.id)
        assert stored.category == FeedbackCategory.PRAISE
        assert stored.status == FeedbackStatus.NEW
        assert stored.message == 'great event!'
        assert stored.page_url == '/volunteer'
