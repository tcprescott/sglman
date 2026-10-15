"""Schemas for the prize payout endpoints.

Money is serialised as a string, never a float: a binary float cannot hold
``0.10`` exactly, and a payout run reading these numbers is entitled to the
cents it was told.
"""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class PayoutLineResponse(BaseModel):
    id: int = Field(..., description="The payout row's ID.")
    place: int = Field(..., description="Finishing place this share pays, starting at 1. Tied places repeat.")
    percentage: Decimal = Field(..., description="Share of the total this place gets, as a percentage (\"25.00\" is 25%).")
    amount: Decimal = Field(
        ..., description="The money this line pays: the percentage of the total, rounded to the cent.",
    )
    entrant_id: Optional[int] = Field(None, description="User ID of the person paid. Null while the split is still a draft.")
    entrant_name: Optional[str] = Field(None, description="Display name of the person paid, or null.")
    matcherino_username: Optional[str] = Field(
        None, description="The person's Matcherino handle, used to send the money. Null when unset or unassigned.",
    )
    note: Optional[str] = Field(None, description="Free-text note on this line.")


class PayoutSplitResponse(BaseModel):
    tournament_id: int = Field(..., description="The tournament this split belongs to.")
    prize_pool: Decimal = Field(..., description="The advertised prize pool. 0.00 when none is set.")
    prize_bonus: Decimal = Field(..., description="The bonus added on top of the pool. 0.00 when none is set.")
    total: Decimal = Field(..., description="Pool plus bonus: what the percentages are taken from.")
    allocated_percentage: Decimal = Field(
        ..., description="Sum of every line's percentage. Below 100 leaves part of the total unassigned.",
    )
    lines: List[PayoutLineResponse] = Field(..., description="One line per paid place, in place order.")


class PayoutLineRequest(BaseModel):
    place: int = Field(..., ge=1, description="Finishing place this share pays, starting at 1.")
    percentage: Decimal = Field(
        ..., gt=0, description="Share of the total for this place, as a percentage above 0. Stored to two decimals.",
    )
    entrant_id: Optional[int] = Field(
        None,
        description=(
            "User ID of the person paid. Leave unset while the split is drafted. Must be a member "
            "of this community, and one person can't be paid twice at the same place."
        ),
    )
    note: Optional[str] = Field(None, description="Free-text note on this line.")


class PayoutSplitRequest(BaseModel):
    lines: List[PayoutLineRequest] = Field(
        ...,
        description=(
            "The whole split, replacing every existing line. The percentages may add up to less "
            "than 100 but not more. An empty list clears the split."
        ),
    )


class PrizePoolRequest(BaseModel):
    prize_pool: Optional[Decimal] = Field(
        None, ge=0, description="The advertised prize pool, rounded to the cent. Null clears it.",
    )
    prize_bonus: Optional[Decimal] = Field(
        None, ge=0, description="A bonus added on top of the pool, rounded to the cent. Null clears it.",
    )
