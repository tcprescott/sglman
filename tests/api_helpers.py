"""Shared helpers for REST API tests.

Provides a full API app (all routers under ``/api``), plus factories to create
a user with a token and an authenticated httpx client. Use together with the
function-scoped ``db`` fixture from conftest.
"""

import random
from typing import Iterable, Optional, Tuple

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import api
from application.services.api_token_service import ApiTokenService
from models import Role, User, UserRole


def build_api_app() -> FastAPI:
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


def client_for(app: FastAPI, raw_token: Optional[str] = None) -> AsyncClient:
    headers = {'Authorization': f'Bearer {raw_token}'} if raw_token else {}
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://test', headers=headers)
