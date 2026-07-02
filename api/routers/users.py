"""User endpoints (read)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import (
    ServiceErrorRoute,
    require_api_actor,
    require_staff,
    require_write_actor,
)
from api.schemas.user_actions import (
    RoleRequest,
    TournamentEnrollmentUpdate,
    UserAdminUpdate,
    UserCreateRequest,
    UserProfileUpdate,
    UserSelfUpdate,
)
from api.schemas.users import UserDetailResponse, UserListItem
from application.services import UserService
from application.services.auth_service import AuthService
from models import Role, User

router = APIRouter(prefix="/users", tags=["Users"], route_class=ServiceErrorRoute)


async def _load_user_or_404(user_id: int) -> User:
    user = await UserService().get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _to_detail(user: User) -> UserDetailResponse:
    roles = await AuthService.get_roles(user)
    return UserDetailResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        discord_id=user.discord_id,
        pronouns=user.pronouns,
        is_active=user.is_active,
        dm_notifications=user.dm_notifications,
        roles=sorted(r.value for r in roles),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get(
    "",
    response_model=List[UserListItem],
    summary="List users",
    description="Staff only. Optionally filter by global role.",
)
async def list_users(
    role: Optional[Role] = Query(None, description="Filter to users holding this global role"),
    actor: User = Depends(require_staff),
):
    return await UserService().get_all_users(role=role)


@router.get("/me", response_model=UserDetailResponse, summary="Get the current user")
async def get_me(actor: User = Depends(require_api_actor)):
    return await _to_detail(actor)


@router.get(
    "/{user_id}",
    response_model=UserDetailResponse,
    summary="Get a user",
    description="Allowed for the user themselves or for Staff.",
)
async def get_user(user_id: int, actor: User = Depends(require_api_actor)):
    if actor.id != user_id and not await AuthService.is_staff(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")
    user = await UserService().get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await _to_detail(user)


# --- Writes -----------------------------------------------------------------


@router.post(
    "",
    response_model=UserDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (Staff only)",
)
async def create_user(body: UserCreateRequest, actor: User = Depends(require_write_actor)):
    user = await UserService().create_user(
        username=body.username,
        actor=actor,
        display_name=body.display_name,
        pronouns=body.pronouns,
        is_active=body.is_active,
        discord_id=body.discord_id,
    )
    return await _to_detail(user)


@router.patch("/me", response_model=UserDetailResponse, summary="Update your own profile")
async def update_me(body: UserSelfUpdate, actor: User = Depends(require_write_actor)):
    await UserService().update_user_personal_info(
        user=actor,
        actor=actor,
        display_name=body.display_name,
        pronouns=body.pronouns,
        dm_notifications=body.dm_notifications,
    )
    return await _to_detail(actor)


@router.patch(
    "/{user_id}",
    response_model=UserDetailResponse,
    summary="Update a user's profile (self or Staff)",
)
async def update_user(user_id: int, body: UserProfileUpdate, actor: User = Depends(require_write_actor)):
    target = await _load_user_or_404(user_id)
    await UserService().update_user_profile(
        user=target, actor=actor, display_name=body.display_name, pronouns=body.pronouns,
    )
    return await _to_detail(target)


@router.patch(
    "/{user_id}/admin",
    response_model=UserDetailResponse,
    summary="Update admin-managed fields (Staff only)",
)
async def update_user_admin(user_id: int, body: UserAdminUpdate, actor: User = Depends(require_write_actor)):
    target = await _load_user_or_404(user_id)
    await UserService().update_user_admin_fields(user=target, actor=actor, is_active=body.is_active)
    return await _to_detail(target)


@router.put(
    "/{user_id}/tournaments",
    summary="Replace a user's tournament enrollments (self or Staff)",
)
async def update_user_tournaments(
    user_id: int, body: TournamentEnrollmentUpdate, actor: User = Depends(require_write_actor),
):
    if actor.id != user_id and not await AuthService.is_staff(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")
    target = await _load_user_or_404(user_id)
    await UserService().manage_tournament_enrollments(
        user=target, actor=actor, tournament_ids=set(body.tournament_ids), is_update=True,
    )
    return {"detail": "Enrollments updated"}


@router.post("/{user_id}/roles", summary="Grant a global role (Staff only)")
async def grant_role(user_id: int, body: RoleRequest, actor: User = Depends(require_write_actor)):
    target = await _load_user_or_404(user_id)
    await UserService().grant_role(target, body.role, actor=actor)
    return {"detail": f"Granted {body.role.value}"}


@router.delete(
    "/{user_id}/roles/{role}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a global role (Staff only)",
)
async def revoke_role(user_id: int, role: Role, actor: User = Depends(require_write_actor)):
    target = await _load_user_or_404(user_id)
    await UserService().revoke_role(target, role, actor=actor)
