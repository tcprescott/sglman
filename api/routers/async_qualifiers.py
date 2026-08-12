"""Async-qualifier endpoints — the self-paced permalink-pool qualifier aggregate.

Mixed auth: admin reads/writes gate ``can_admin_qualifier`` in the service, player
run methods enforce ownership on the resolved actor, and the public shell / open
list are ungated by design (a valid token is still required). Every read uses the
``require_api_actor`` (A) dependency and every write ``require_write_actor`` (W).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from api._helpers import load_user_or_404
from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.async_qualifiers import (
    AdminRequest,
    AsyncQualifierPermalinkResponse,
    AsyncQualifierPoolResponse,
    AsyncQualifierPublicResponse,
    AsyncQualifierResponse,
    AsyncQualifierReviewNoteResponse,
    AsyncQualifierRunPage,
    AsyncQualifierRunResponse,
    LeaderboardEntryResponse,
    MyQualifierRunResponse,
    PermalinkBulkRequest,
    PermalinkBulkResponse,
    PermalinkCreateRequest,
    PermalinkRollRequest,
    PermalinkUpdateRequest,
    PoolCreateRequest,
    PoolUpdateRequest,
    QualifierCreateRequest,
    QualifierUpdateRequest,
    ReattemptRequest,
    RejectedPermalinkLine,
    ReviewRequest,
    StartRunRequest,
    SubmitRunRequest,
)
from api.schemas.common import UserBase
from application.errors import require_found
from application.services import AsyncQualifierService
from application.tenant_context import require_tenant_id
from models import AsyncQualifier, User

router = APIRouter(prefix="/async-qualifiers", tags=["Async qualifiers"], route_class=ServiceErrorRoute)

# One page of runs, and the most a caller may ask for at once. A 500-player
# qualifier holds a few thousand runs, so the unbounded read this replaces was a
# 1.66 MB body every time.
RUNS_PAGE_DEFAULT = 100
RUNS_PAGE_MAX = 500


async def _load_qualifier_or_404(qualifier_id: int) -> AsyncQualifier:
    return require_found(
        await AsyncQualifier.get_or_none(id=qualifier_id, tenant_id=require_tenant_id()),
        "Qualifier",
    )


# ============================================================ reads (A)

@router.get("", response_model=List[AsyncQualifierResponse], summary="List qualifiers (admin)")
async def list_qualifiers(actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().list_qualifiers(actor)


@router.get("/open", response_model=List[AsyncQualifierPublicResponse], summary="List open (active) qualifiers")
async def list_open_qualifiers(actor: User = Depends(require_api_actor)):
    # Ungated player-facing list: the public shell only (no internal ``config``).
    return await AsyncQualifierService().list_open_qualifiers()


@router.get("/{qualifier_id}", response_model=AsyncQualifierResponse, summary="Get a qualifier (admin)")
async def get_qualifier(qualifier_id: int, actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().get_qualifier(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/public",
    response_model=AsyncQualifierPublicResponse,
    summary="Get a qualifier's public shell",
)
async def get_qualifier_public(qualifier_id: int, actor: User = Depends(require_api_actor)):
    # Ungated player shell: the public response model omits the internal ``config``.
    return await AsyncQualifierService().get_qualifier_for_player(qualifier_id)


@router.get(
    "/{qualifier_id}/admins",
    response_model=List[UserBase],
    summary="List a qualifier's admins/reviewers",
)
async def list_admins(qualifier_id: int, actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().list_admins(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/pools",
    response_model=List[AsyncQualifierPoolResponse],
    summary="List a qualifier's pools (admin)",
)
async def list_pools(qualifier_id: int, actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().list_pools(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/pools/available",
    response_model=List[AsyncQualifierPoolResponse],
    summary="Pools the caller may still draw from",
)
async def get_player_pools(qualifier_id: int, actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().get_player_pools(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/review-queue",
    response_model=List[AsyncQualifierRunResponse],
    summary="Runs pending review (admin)",
)
async def list_review_queue(qualifier_id: int, actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().list_review_queue(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/runs",
    response_model=AsyncQualifierRunPage,
    summary="Runs in the qualifier, newest first (admin)",
)
async def list_runs(
    qualifier_id: int,
    limit: int = Query(RUNS_PAGE_DEFAULT, ge=1, le=RUNS_PAGE_MAX,
                       description="Maximum runs to return."),
    offset: int = Query(0, ge=0),
    actor: User = Depends(require_api_actor),
):
    """One page of runs, plus the qualifier's total.

    Paginated because it was not: a 500-player qualifier answered this with 3,129
    runs in a 1.66 MB body, every time, and a caller that wanted the ten most recent
    had no way to say so. ``total`` is how many exist, not how many came back.
    """
    service = AsyncQualifierService()
    return AsyncQualifierRunPage(
        total=await service.count_runs(actor, qualifier_id),
        limit=limit,
        offset=offset,
        items=[
            AsyncQualifierRunResponse.model_validate(run)
            for run in await service.list_runs(actor, qualifier_id, limit=limit, offset=offset)
        ],
    )


@router.get(
    "/{qualifier_id}/leaderboard",
    response_model=List[LeaderboardEntryResponse],
    summary="Qualifier leaderboard (hidden while open for non-admins)",
)
async def get_leaderboard(qualifier_id: int, actor: User = Depends(require_api_actor)):
    return await AsyncQualifierService().get_leaderboard(actor, qualifier_id)


@router.get(
    "/{qualifier_id}/me/runs",
    response_model=List[MyQualifierRunResponse],
    summary="The caller's runs in a qualifier",
)
async def list_my_runs(qualifier_id: int, actor: User = Depends(require_api_actor)):
    """The caller's own runs, in the caller's own projection.

    Narrower than the reviewer's ``/{id}/runs`` on purpose: an exact score plus
    the caller's own elapsed time solves for the seed's par, which the
    active-window lockdown exists to hide, so ``score`` is null and ``score_band``
    stands in until the qualifier closes.
    """
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
    return await AsyncQualifierService().update_qualifier(
        actor, qualifier_id, **body.model_dump(exclude_unset=True)
    )


@router.delete(
    "/{qualifier_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a qualifier",
)
async def delete_qualifier(qualifier_id: int, actor: User = Depends(require_write_actor)):
    await AsyncQualifierService().delete_qualifier(actor, qualifier_id)


@router.post(
    "/{qualifier_id}/admins",
    status_code=status.HTTP_201_CREATED,
    summary="Grant a user admin/reviewer on a qualifier",
)
async def add_admin(qualifier_id: int, body: AdminRequest, actor: User = Depends(require_write_actor)):
    target = await load_user_or_404(body.user_id)
    await AsyncQualifierService().add_admin(actor, qualifier_id, target)


@router.delete(
    "/{qualifier_id}/admins/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a user's admin/reviewer on a qualifier",
)
async def remove_admin(qualifier_id: int, user_id: int, actor: User = Depends(require_write_actor)):
    target = await load_user_or_404(user_id)
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
    response_model=PermalinkBulkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add many permalinks to a pool",
)
async def add_permalinks_bulk(
    pool_id: int, body: PermalinkBulkRequest, actor: User = Depends(require_write_actor),
):
    """Add one permalink per usable line, and report the lines that were not.

    A line that is not an http(s) URL is skipped rather than failing the whole
    paste, and comes back in ``rejected`` with its position and the reason — a
    count alone made a typo indistinguishable from a success.
    """
    result = await AsyncQualifierService().add_permalinks_bulk(actor, pool_id, urls=body.urls)
    return PermalinkBulkResponse(
        created=[AsyncQualifierPermalinkResponse.model_validate(p) for p in result.created],
        rejected=[
            RejectedPermalinkLine(line=number, value=value, reason=reason)
            for number, value, reason in result.rejected
        ],
    )


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


@router.post(
    "/runs/{run_id}/grant-reattempt",
    response_model=AsyncQualifierRunResponse,
    summary="Grant a reattempt on a runner's behalf (admin, ignores their allowance)",
)
async def grant_reattempt(run_id: int, body: ReattemptRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierService().grant_reattempt(actor, run_id, reason=body.reason)


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
