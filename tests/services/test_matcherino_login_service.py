"""The saved Matcherino login: checked before it is stored, never echoed, and used by the sync."""

import json

import pytest

from application.errors import FeatureDisabledError
from application.services.check_in_service import CheckInService
from application.services.matcherino_login_service import MatcherinoLoginService
from application.utils.clients.matcherino_client import (
    MatcherinoAPIError,
    MatcherinoAuthError,
    MockMatcherinoClient,
)
from models import AuditLog, FeatureFlag, MatcherinoLogin, Role, TenantFeatureFlag
from tests.conftest import DEFAULT_TEST_TENANT_ID
from tests.services.check_in_support import VENUE, with_role

TOKEN = 'b7e1c2d4-0000-4000-8000-1234567890ab'


class FakeClient:
    def __init__(self, outcome):
        self.outcome = outcome

    async def verify_login(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _service(outcome='4321', seen=None):
    def factory(token):
        if seen is not None:
            seen.append(token)
        return FakeClient(outcome)
    return MatcherinoLoginService(client_factory=factory)


@pytest.fixture
async def staff(db):
    return await with_role(1, 'staff', Role.STAFF)


async def test_a_token_matcherino_accepts_is_saved_with_its_account(staff):
    seen = []
    status = await _service(seen=seen).set_login(staff, f'  {TOKEN}  ')

    assert seen == [TOKEN]
    assert (status.configured, status.matcherino_user_id, status.updated_by) == (True, '4321', 'staff')
    login = await MatcherinoLogin.get(tenant_id=DEFAULT_TEST_TENANT_ID)
    assert login.refresh_token == TOKEN


async def test_the_devtools_request_payload_is_accepted_as_pasted(staff):
    seen = []
    await _service(seen=seen).set_login(staff, json.dumps({'appName': 'WEB', 'refreshToken': TOKEN}))
    assert seen == [TOKEN]


@pytest.mark.parametrize('outcome, message', [
    (MatcherinoAuthError('refused'), "didn't accept that token"),
    (MatcherinoAPIError('down'), "Couldn't check that token"),
])
async def test_a_token_matcherino_rejects_is_not_saved(staff, outcome, message):
    with pytest.raises(ValueError, match=message):
        await _service(outcome).set_login(staff, TOKEN)
    assert not await MatcherinoLogin.exists()


@pytest.mark.parametrize('pasted', ['', '   ', '{"appName": "WEB"}', 'two words', 'x' * 513])
async def test_a_blank_or_malformed_paste_never_reaches_matcherino(staff, pasted):
    seen = []
    with pytest.raises(ValueError):
        await _service(seen=seen).set_login(staff, pasted)
    assert seen == []


async def test_replacing_and_clearing_are_audited_without_the_token(staff):
    service = _service()
    await service.set_login(staff, TOKEN)
    await service.set_login(staff, TOKEN + 'f')
    await service.clear_login(staff)
    await service.clear_login(staff)

    assert await MatcherinoLogin.filter(tenant_id=DEFAULT_TEST_TENANT_ID).count() == 0
    rows = await AuditLog.filter(action__startswith='matcherino_login.').order_by('id')
    assert [(r.action, json.loads(r.details).get('replaced')) for r in rows] == [
        ('matcherino_login.set', False), ('matcherino_login.set', True), ('matcherino_login.cleared', None),
    ]
    assert not any(TOKEN in r.details for r in rows)


async def test_status_never_carries_the_token(staff):
    await _service().set_login(staff, TOKEN)
    status = await _service().status(staff)
    assert TOKEN not in repr(status)


@pytest.mark.parametrize('role', [Role.CHECK_IN_DESK, Role.VOLUNTEER])
async def test_only_staff_manage_the_login(db, role):
    user = await with_role(5, 'not-staff', role)
    service = _service()
    for call in (service.status(user), service.set_login(user, TOKEN), service.clear_login(user)):
        with pytest.raises(PermissionError):
            await call
    assert not await MatcherinoLogin.exists()


async def test_the_login_is_refused_with_check_in_off(staff):
    from application.services.feature_flag_service import reset_flag_cache

    await TenantFeatureFlag.filter(
        tenant_id=DEFAULT_TEST_TENANT_ID, flag=FeatureFlag.EVENT_CHECK_IN.value,
    ).update(enabled=False)
    reset_flag_cache()
    with pytest.raises(FeatureDisabledError):
        await _service().set_login(staff, TOKEN)


async def test_the_sync_signs_in_with_the_saved_login(staff, monkeypatch):
    await MatcherinoLogin.create(tenant_id=DEFAULT_TEST_TENANT_ID, refresh_token=TOKEN)
    seen = []

    def factory(refresh_token):
        seen.append(refresh_token)
        return MockMatcherinoClient()

    monkeypatch.setattr('application.services.check_in_service.get_matcherino_client', factory)
    service = CheckInService()
    event = await service.create_event(staff, 'SGL 2026', venue_id=VENUE)
    await service.sync_event(staff, event.id)

    assert seen == [TOKEN]


async def test_with_no_saved_login_the_sync_says_where_to_add_one(staff):
    service = CheckInService()
    event = await service.create_event(staff, 'SGL 2026', venue_id=VENUE)
    with pytest.raises(ValueError, match='Admin → Check-in'):
        await service.sync_event(staff, event.id)
    await event.refresh_from_db()
    assert 'no Matcherino login is saved' in event.last_sync_error
