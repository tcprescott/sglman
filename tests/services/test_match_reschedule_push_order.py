"""The order of an approval's writes and its live push.

Split from ``test_match_reschedule_service.py``, which sits at the file-length
guardrail.
"""

from application.services import MatchRescheduleService
from tests.services.test_match_reschedule_service import _match, _soon, _staff, _submit


class TestApprovalPushOrder:
    async def test_approving_nudges_after_the_decision_is_recorded(self, db, monkeypatch):
        """update_match publishes before the request is marked approved, so a
        board refreshing on that push read it as half-decided and showed neither
        "Change requested" nor Ask to change. A push must follow the status write."""
        from application.events import match_live

        m, p1, _ = await _match()
        boss = await _staff()
        request = await _submit(m, p1, proposed_at=_soon())
        order = []
        monkeypatch.setattr(
            match_live, 'publish',
            lambda match_id, change_type=match_live.CHANGED: order.append(('push', match_id)),
        )
        service = MatchRescheduleService()
        real_update = service.repository.update

        async def recording_update(*args, **kwargs):
            result = await real_update(*args, **kwargs)
            order.append(('status', kwargs.get('status')))
            return result

        monkeypatch.setattr(service.repository, 'update', recording_update)

        await service.approve(request.id, boss)

        status_at = next(i for i, e in enumerate(order) if e[0] == 'status')
        assert ('push', m.id) in order[status_at:]
