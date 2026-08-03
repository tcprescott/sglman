"""Prize payout endpoints — the pool and the placement split."""

from fastapi import APIRouter, Depends

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.payouts import (
    PayoutLineResponse,
    PayoutSplitRequest,
    PayoutSplitResponse,
    PrizePoolRequest,
)
from application.services import PayoutService
from application.services.payout_service import PayoutSplit
from models import User

router = APIRouter(prefix="/tournaments", tags=["Payouts"], route_class=ServiceErrorRoute)


def _to_response(tournament_id: int, split: PayoutSplit) -> PayoutSplitResponse:
    return PayoutSplitResponse(
        tournament_id=tournament_id,
        prize_pool=split.pool,
        prize_bonus=split.bonus,
        total=split.total,
        allocated_percentage=split.allocated_percentage,
        lines=[
            PayoutLineResponse(
                id=line.payout.id,
                place=line.place,
                percentage=line.percentage,
                amount=line.amount,
                entrant_id=line.payout.entrant_id,  # type: ignore[attr-defined]
                entrant_name=line.entrant_name,
                matcherino_username=line.matcherino_username,
                note=line.payout.note,
            )
            for line in split.lines
        ],
    )


@router.get(
    "/{tournament_id}/payouts",
    response_model=PayoutSplitResponse,
    summary="Get a tournament's prize split, with the amounts worked out",
    description="Requires Staff or Tournament Admin of the given tournament.",
)
async def get_payouts(tournament_id: int, actor: User = Depends(require_api_actor)):
    split = await PayoutService().get_split(tournament_id, actor)
    return _to_response(tournament_id, split)


@router.put(
    "/{tournament_id}/payouts",
    response_model=PayoutSplitResponse,
    summary="Replace a tournament's prize split",
)
async def replace_payouts(
    tournament_id: int,
    body: PayoutSplitRequest,
    actor: User = Depends(require_write_actor),
):
    split = await PayoutService().set_split(
        tournament_id, [line.model_dump() for line in body.lines], actor,
    )
    return _to_response(tournament_id, split)


@router.put(
    "/{tournament_id}/prize-pool",
    response_model=PayoutSplitResponse,
    summary="Set a tournament's prize pool and bonus",
)
async def set_prize_pool(
    tournament_id: int,
    body: PrizePoolRequest,
    actor: User = Depends(require_write_actor),
):
    service = PayoutService()
    await service.set_pool(tournament_id, body.prize_pool, body.prize_bonus, actor)
    return _to_response(tournament_id, await service.get_split(tournament_id, actor))
