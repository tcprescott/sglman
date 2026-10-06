"""Shared pieces for the check-in service tests: a scripted Matcherino client and fixtures."""

import pytest

from application.services.check_in_service import CheckInService
from application.utils.clients.matcherino_client import MockMatcherinoClient
from models import CheckInEntrant, CheckInEventStatus, Role, User, UserRole
from tests.conftest import DEFAULT_TEST_TENANT_ID
from tests.factories import make_user

VENUE = 182105


class ScriptedClient(MockMatcherinoClient):
    """A mock whose sales a test can change between syncs, or make fail."""

    def __init__(self, purchases):
        super().__init__(purchases)
        self.error = None

    def set(self, purchases, tiers=None):
        self._purchases = purchases
        if tiers is not None:
            self._tiers = tiers

    async def fetch_sales(self, venue_id):
        if self.error is not None:
            raise self.error
        return await super().fetch_sales(venue_id)


async def with_role(discord_id: int, username: str, role: Role) -> User:
    user = await make_user(discord_id=discord_id, username=username)
    await UserRole.create(user=user, role=role, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


@pytest.fixture
async def staff(db):
    return await with_role(1, 'staff', Role.STAFF)


@pytest.fixture
async def desk(db):
    return await with_role(2, 'desk', Role.CHECK_IN_DESK)


@pytest.fixture
def client():
    return ScriptedClient([])


@pytest.fixture
def service(client):
    return CheckInService(client=client)


@pytest.fixture
async def event(service, staff):
    return await service.create_event(staff, 'SGL 2026', venue_id=VENUE, status=CheckInEventStatus.OPEN)


async def rows(event):
    return {row.matcherino_user_id: row for row in await CheckInEntrant.filter(event=event)}
