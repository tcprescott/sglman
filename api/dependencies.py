"""Shared FastAPI dependencies and error handling for the REST API.

Authentication is via a personal bearer token (``Authorization: Bearer
sglman_pat_...``) generated on the user's profile page. A token resolves to
its owning :class:`User` and the request then runs the *same* service-layer
permission checks as the web UI. A token flagged ``read_only`` may only call
read (GET) endpoints.

``ServiceErrorRoute`` translates the service layer's ``PermissionError`` /
``ValueError`` into ``403`` / ``400`` responses. It is scoped to the API
routers (via ``route_class``) so it never affects the NiceGUI frontend mounted
on the same app.
"""

from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from application.services.api_token_service import ApiTokenService
from application.services.auth_service import AuthService
from models import ApiToken, User

# auto_error=False so a missing/malformed header yields our own 401 (FastAPI's
# default for HTTPBearer is a 403), keeping all auth failures consistent.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Personal API token generated on your profile page.",
)


async def _resolve_token(creds: Optional[HTTPAuthorizationCredentials]) -> Tuple[User, ApiToken]:
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    result = await ApiTokenService().authenticate(creds.credentials)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, token = result
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        )
    return user, token


async def require_api_actor(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    """Resolve the authenticated user from the bearer token (any token)."""
    user, _ = await _resolve_token(creds)
    return user


async def require_write_actor(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    """Resolve the user and reject read-only tokens. Use on mutating routes."""
    user, token = await _resolve_token(creds)
    if token.read_only:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This token is read-only and cannot perform write actions",
        )
    return user


async def require_admin(actor: User = Depends(require_api_actor)) -> User:
    """Authenticated user who can view the admin area (any global role or
    tournament admin/crew-coordinator membership)."""
    await AuthService.ensure(
        await AuthService.can_view_admin(actor), "Admin access required"
    )
    return actor


async def require_staff(actor: User = Depends(require_api_actor)) -> User:
    """Authenticated user holding the global STAFF role."""
    await AuthService.ensure(
        await AuthService.is_staff(actor), "Staff access required"
    )
    return actor


class ServiceErrorRoute(APIRoute):
    """Translate service-layer exceptions into HTTP responses.

    - ``PermissionError`` -> 403
    - ``ValueError``      -> 400
    """

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def custom_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except PermissionError as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=str(exc) or "Permission denied",
                ) from exc
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc

        return custom_handler
