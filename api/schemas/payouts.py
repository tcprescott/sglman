"""Schemas for the prize payout endpoints.

Money is serialised as a string, never a float: a binary float cannot hold
``0.10`` exactly, and a payout run reading these numbers is entitled to the
cents it was told.
"""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class PayoutLineResponse(BaseModel):
    id: int
    place: int
    percentage: Decimal
    amount: Decimal
    entrant_id: Optional[int] = None
    entrant_name: Optional[str] = None
    matcherino_username: Optional[str] = None
    note: Optional[str] = None


class PayoutSplitResponse(BaseModel):
    tournament_id: int
    prize_pool: Decimal
    prize_bonus: Decimal
    total: Decimal
    allocated_percentage: Decimal
    lines: List[PayoutLineResponse]


class PayoutLineRequest(BaseModel):
    place: int = Field(..., ge=1)
    percentage: Decimal = Field(..., gt=0)
    entrant_id: Optional[int] = Field(
        None, description="Leave unset while the split is drafted"
    )
    note: Optional[str] = None


class PayoutSplitRequest(BaseModel):
    lines: List[PayoutLineRequest]


class PrizePoolRequest(BaseModel):
    prize_pool: Optional[Decimal] = Field(None, ge=0)
    prize_bonus: Optional[Decimal] = Field(None, ge=0)
