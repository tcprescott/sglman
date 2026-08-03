"""Shared helpers for REST API tests.

Provides a full API app (all routers under ``/api``), plus factories to create
a user with a token and an authenticated httpx client. Use together with the
function-scoped ``db`` fixture from conftest.
"""

import functools
import random
from typing import Iterable, Optional, Tuple

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import api
from application.repositories._tenant import current_tenant_id
from application.repositories.tenant_membership_repository import (
    TenantMembershipRepository,
)
from application.services.api_token_service import ApiTokenService
from models import Role, User, UserRole


@functools.cache
def build_api_app() -> FastAPI:
    """The full API app, built once per process and shared by every test.

    ``include_router`` costs ~200ms — it resolves each route's dependency graph
    and builds a Pydantic response model per endpoint — and the result is a pure
    function of ``api.router``, which no test mutates (nothing in the suite
    touches ``dependency_overrides``, ``app.state``, or adds middleware to this
    app). Rebuilding it per test cost more than every DB query in the suite
    combined, so it is cached. A test that genuinely needs a throwaway app
    builds its own ``FastAPI()`` instead (see ``test_tenant_middleware.py``).
    """
    app = FastAPI()
    app.include_router(api.router, prefix='/api')
    return app


async def create_user_token(
    *,
    username: str = 'user',
    discord_id: Optional[int] = None,
    roles: Optional[Iterable[Role]] = None,
    read_only: bool = False,
    is_active: bool = True,
) -> Tuple[User, str]:
    """Create a user (optionally with global roles) and a token for them.

    Returns (user, raw_token).
    """
    if discord_id is None:
        discord_id = random.randint(1, 10 ** 12)
    user = await User.create(discord_id=discord_id, username=username, is_active=is_active)
    for role in roles or []:
        # SUPER_ADMIN is the one *global* role (``UserRole`` with ``tenant=None``);
        # pass tenant explicitly so the db-fixture's auto-stamp leaves it NULL.
        # Every other role is tenant-scoped and stamped with the ambient tenant.
        if role == Role.SUPER_ADMIN:
            await UserRole.create(user=user, role=role, tenant=None)
        else:
            await UserRole.create(user=user, role=role)
    _, raw_token = await ApiTokenService().create_token(user, name='test', read_only=read_only)
    return user, raw_token


async def create_community_member(
    *, username: str = 'member', discord_id: Optional[int] = None,
) -> User:
    """A user who belongs to the ambient tenant, like a real one does.

    A bare ``User.create`` produces an account with no ``TenantMembership``,
    which no community can see: the person pickers read
    ``get_community_people`` (membership-based) and the by-id routes now scope to
    the same basis. A test that wants "another person in this community" wants
    this; a test that wants "someone from elsewhere" keeps ``User.create``.
    """
    if discord_id is None:
        discord_id = random.randint(1, 10 ** 12)
    user = await User.create(discord_id=discord_id, username=username)
    await TenantMembershipRepository.add(user, current_tenant_id())
    return user


async def enable_all_features(tenant_id: int) -> None:
    """Provision every feature flag (available+enabled) for a tenant.

    New tenants start with all features OFF (the production default), so a test
    that spins up a *second* tenant to hit a feature-gated router must provision
    it — the ``db`` fixture already does this for the default tenant (id 1).
    """
    from models import FeatureFlag, TenantFeatureFlag
    for flag in FeatureFlag:
        await TenantFeatureFlag.get_or_create(
            tenant_id=tenant_id, flag=flag.value,
            defaults={'available': True, 'enabled': True},
        )


def client_for(app: FastAPI, raw_token: Optional[str] = None) -> AsyncClient:
    headers = {'Authorization': f'Bearer {raw_token}'} if raw_token else {}
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://test', headers=headers)
