"""Async-qualifier endpoints — the self-paced permalink-pool qualifier aggregate.

Mixed auth: admin reads/writes gate ``can_admin_qualifier`` in the service, player
run methods enforce ownership on the resolved actor, and the public shell / open
list are ungated by design (a valid token is still required). Every read uses the
``require_api_actor`` (A) dependency and every write ``require_write_actor`` (W).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.async_qualifiers import (
    AdminRequest,
    AsyncQualifierPermalinkResponse,
    AsyncQualifierPoolResponse,
    AsyncQualifierResponse,
    AsyncQualifierReviewNoteResponse,
    AsyncQualifierRunResponse,
    LeaderboardEntryResponse,
    PermalinkBulkRequest,
    PermalinkCreateRequest,
    PermalinkRollRequest,
    PermalinkUpdateRequest,
    PoolCreateRequest,
    PoolUpdateRequest,
    QualifierCreateRequest,
    QualifierUpdateRequest,
    ReattemptRequest,
    ReviewRequest,
    StartRunRequest,
    SubmitRunRequest,
)
from api.schemas.common import UserBase
from application.services import AsyncQualifierService, UserService
from application.tenant_context import require_tenant_id
from models import AsyncQualifier, User

router = APIRouter(prefix="/async-qualifiers", tags=["Async qualifiers"], route_class=ServiceErrorRoute)


async def _load_qualifier_or_404(qualifier_id: int) -> AsyncQualifier:
    qualifier = await AsyncQualifier.get_or_none(id=qualifier_id, tenant_id=require_tenant_id())
    if qualifier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Qualifier not found")
    return qualifier


async def _load_user_or_404(user_id: int) -> User:
    user = await UserService().get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# ============================================================ reads (A)

@router.get("", response_model=List[AsyncQualifierResponse], summary="List qualifiers (admin)")
async def list_qualifiers(actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().list_qualifiers(actor)


@router.get("/open", response_model=List[AsyncQualifierResponse], summary="List open (active) qualifiers")
async def list_open_qualifiers(actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().list_open_qualifiers()


@router.get("/{qualifier_id}", response_model=AsyncQualifierResponse, summary="Get a qualifier (admin)")
async def get_qualifier(qualifier_id: int, actor: User = Depends(require_api_actor)):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().get_qualifier(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/public",
    response_model=AsyncQualifierResponse,
    summary="Get a qualifier's public shell",
)
async def get_qualifier_public(qualifier_id: int, actor: User = Depends(require_api_actor)):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().get_qualifier_for_player(qualifier_id)


@router.get(
    "/{qualifier_id}/admins",
    response_model=List[UserBase],
    summary="List a qualifier's admins/reviewers",
)
async def list_admins(qualifier_id: int, actor: User = Depends(require_api_actor)):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().list_admins(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/pools",
    response_model=List[AsyncQualifierPoolResponse],
    summary="List a qualifier's pools (admin)",
)
async def list_pools(qualifier_id: int, actor: User = Depends(require_api_actor)):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().list_pools(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/pools/available",
    response_model=List[AsyncQualifierPoolResponse],
    summary="Pools the caller may still draw from",
)
async def get_player_pools(qualifier_id: int, actor: User = Depends(require_api_actor)):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().get_player_pools(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/review-queue",
    response_model=List[AsyncQualifierRunResponse],
    summary="Runs pending review (admin)",
)
async def list_review_queue(qualifier_id: int, actor: User = Depends(require_api_actor)):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().list_review_queue(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/leaderboard",
    response_model=List[LeaderboardEntryResponse],
    summary="Qualifier leaderboard (hidden while open for non-admins)",
)
async def get_leaderboard(qualifier_id: int, actor: User = Depends(require_api_actor)):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().get_leaderboard(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/me/runs",
    response_model=List[AsyncQualifierRunResponse],
    summary="The caller's runs in a qualifier",
)
async def list_my_runs(qualifier_id: int, actor: User = Depends(require_api_actor)):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().list_user_runs(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/me/active-run",
    response_model=Optional[AsyncQualifierRunResponse],
    summary="The caller's active run (or null)",
)
async def get_my_active_run(qualifier_id: int, actor: User = Depends(require_api_actor)):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().get_active_run(actor, qualifier_id)


@router.get(
    "/runs/{run_id}/notes",
    response_model=List[AsyncQualifierReviewNoteResponse],
    summary="Review notes on a run",
)
async def get_run_notes(run_id: int, actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().get_run_notes(actor, run_id)


# ============================================================ writes (W)

@router.post(
    "",
    response_model=AsyncQualifierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a qualifier",
)
async def create_qualifier(body: QualifierCreateRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().create_qualifier(actor, **body.model_dump())


@router.patch("/{qualifier_id}", response_model=AsyncQualifierResponse, summary="Update a qualifier")
async def update_qualifier(
    qualifier_id: int, body: QualifierUpdateRequest, actor: User = Depends(require_write_actor),
):
    await _load_qualifier_or_404(qualifier_id)
    return await AsyncQualifierService().update_qualifier(
        actor, qualifier_id, **body.model_dump(exclude_unset=True)
    )


@router.delete(
    "/{qualifier_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a qualifier",
)
async def delete_qualifier(qualifier_id: int, actor: User = Depends(require_write_actor)):
    await _load_qualifier_or_404(qualifier_id)
    await AsyncQualifierService().delete_qualifier(actor, qualifier_id)


@router.post(
    "/{qualifier_id}/admins",
    status_code=status.HTTP_201_CREATED,
    summary="Grant a user admin/reviewer on a qualifier",
)
async def add_admin(qualifier_id: int, body: AdminRequest, actor: User = Depends(require_write_actor)):
    target = await _load_user_or_404(body.user_id)
    await AsyncQualifierService().add_admin(actor, qualifier_id, target)


@router.delete(
    "/{qualifier_id}/admins/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a user's admin/reviewer on a qualifier",
)
async def remove_admin(qualifier_id: int, user_id: int, actor: User = Depends(require_write_actor)):
    target = await _load_user_or_404(user_id)
    await AsyncQualifierService().remove_admin(actor, qualifier_id, target)


# --- pools ---

@router.post(
    "/{qualifier_id}/pools",
    response_model=AsyncQualifierPoolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pool",
)
async def create_pool(qualifier_id: int, body: PoolCreateRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().create_pool(actor, qualifier_id, **body.model_dump())


@router.patch("/pools/{pool_id}", response_model=AsyncQualifierPoolResponse, summary="Update a pool")
async def update_pool(pool_id: int, body: PoolUpdateRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().update_pool(actor, pool_id, **body.model_dump(exclude_unset=True))


@router.delete("/pools/{pool_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a pool")
async def delete_pool(pool_id: int, actor: User = Depends(require_write_actor)):
    await AsyncQualifierService().delete_pool(actor, pool_id)


# --- permalinks ---

@router.post(
    "/pools/{pool_id}/permalinks",
    response_model=AsyncQualifierPermalinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a permalink to a pool",
)
async def add_permalink(pool_id: int, body: PermalinkCreateRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().add_permalink(actor, pool_id, **body.model_dump())


@router.post(
    "/pools/{pool_id}/permalinks/bulk",
    response_model=List[AsyncQualifierPermalinkResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add many permalinks to a pool",
)
async def add_permalinks_bulk(
    pool_id: int, body: PermalinkBulkRequest, actor: User = Depends(require_write_actor),
):
    return await AsyncQualifierService().add_permalinks_bulk(actor, pool_id, urls=body.urls)


@router.post(
    "/pools/{pool_id}/permalinks/roll",
    response_model=List[AsyncQualifierPermalinkResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Roll fresh seeds into a pool from its preset",
)
async def roll_permalinks(
    pool_id: int, body: PermalinkRollRequest, actor: User = Depends(require_write_actor),
):
    return await AsyncQualifierService().roll_permalinks(actor, pool_id, count=body.count)


@router.patch(
    "/permalinks/{permalink_id}",
    response_model=AsyncQualifierPermalinkResponse,
    summary="Update a permalink",
)
async def update_permalink(
    permalink_id: int, body: PermalinkUpdateRequest, actor: User = Depends(require_write_actor),
):
    return await AsyncQualifierService().update_permalink(
        actor, permalink_id, **body.model_dump(exclude_unset=True)
    )


@router.delete(
    "/permalinks/{permalink_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a permalink",
)
async def delete_permalink(permalink_id: int, actor: User = Depends(require_write_actor)):
    await AsyncQualifierService().delete_permalink(actor, permalink_id)


# --- player run lifecycle ---

@router.post(
    "/{qualifier_id}/runs",
    response_model=AsyncQualifierRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start (draw) a run in a pool",
)
async def start_run(qualifier_id: int, body: StartRunRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().start_run(actor, qualifier_id, body.pool_id)


@router.post("/runs/{run_id}/submit", response_model=AsyncQualifierRunResponse, summary="Submit a finished run")
async def submit_run(run_id: int, body: SubmitRunRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().submit_run(
        actor, run_id, elapsed_seconds=body.elapsed_seconds, runner_vod_url=body.runner_vod_url
    )


@router.post("/runs/{run_id}/forfeit", response_model=AsyncQualifierRunResponse, summary="Forfeit a run")
async def forfeit_run(run_id: int, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().forfeit_run(actor, run_id)


@router.post("/runs/{run_id}/reattempt", response_model=AsyncQualifierRunResponse, summary="Reattempt a run")
async def reattempt_run(run_id: int, body: ReattemptRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().reattempt_run(actor, run_id, reason=body.reason)


# --- review ---

@router.post("/runs/{run_id}/claim", response_model=AsyncQualifierRunResponse, summary="Claim a run for review")
async def claim_run(run_id: int, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().claim_run(actor, run_id)


@router.post("/runs/{run_id}/release", response_model=AsyncQualifierRunResponse, summary="Release a review claim")
async def release_claim(run_id: int, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().release_claim(actor, run_id)


@router.post("/runs/{run_id}/review", response_model=AsyncQualifierRunResponse, summary="Approve or reject a run")
async def review_run(run_id: int, body: ReviewRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().review_run(
        actor, run_id, approved=body.approved, note=body.note
    )
