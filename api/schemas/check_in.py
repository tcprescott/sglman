"""Schemas for the check-in desk endpoints."""

from datetime import datetime
from typing import Iterable, List, Optional

from pydantic import BaseModel, Field

from application.services.check_in_rules import active_badges, lanyard_for
from models import CheckInEntrant, CheckInEvent


def _value(enum_or_none) -> Optional[str]:
    return getattr(enum_or_none, 'value', enum_or_none)


class CheckInEventResponse(BaseModel):
    id: int
    name: str
    status: str
    matcherino_venue_id: Optional[int] = None
    last_synced_at: Optional[datetime] = None
    last_sync_error: Optional[str] = None
    last_sync_count: Optional[int] = None

    @classmethod
    def from_row(cls, event: CheckInEvent) -> 'CheckInEventResponse':
        return cls(
            id=event.id,
            name=event.name,
            status=_value(event.status) or '',
            matcherino_venue_id=event.matcherino_venue_id,
            last_synced_at=event.last_synced_at,
            last_sync_error=event.last_sync_error,
            last_sync_count=event.last_sync_count,
        )


class CheckInEntrantResponse(BaseModel):
    id: int
    event_id: int
    display_name: str
    source: str = Field(description="`matcherino`, `walk_up` or `comp`.")
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    link_method: Optional[str] = None
    badges: List[str] = Field(
        default_factory=list,
        description="Badge types they still hold, most expensive first. Empty for a walk-up or a comp.",
    )
    lanyard: Optional[str] = Field(
        default=None,
        description="The lanyard the desk hands over (`staff`, `volunteer`, or a badge type's), or null.",
    )
    comp_reasons: List[str] = Field(default_factory=list)
    withdrawn_at: Optional[datetime] = Field(
        default=None,
        description="Set when they no longer hold a badge. Only staff can check them in anyway.",
    )
    checked_in_at: Optional[datetime] = None
    checked_in_by_name: Optional[str] = None
    dm_status: Optional[str] = Field(
        default=None,
        description=(
            "The check-in test DM: `pending`, `sent`, `blocked` (Discord refused: DMs closed or no "
            "shared server), `opted_out` (DMs off in Wizzrobe) or `failed` (Discord didn't answer). "
            "Null until they're checked in with a linked account."
        ),
    )

    @classmethod
    def from_row(
        cls, entrant: CheckInEntrant, volunteer_ids: Iterable[int] = (),
    ) -> 'CheckInEntrantResponse':
        """``passes__tier``, ``user`` and ``checked_in_by`` must be prefetched."""
        held = active_badges(entrant.passes)
        user = entrant.user
        checker = entrant.checked_in_by
        return cls(
            id=entrant.id,
            event_id=entrant.event_id,
            display_name=entrant.display_name,
            source=_value(entrant.source) or '',
            user_id=entrant.user_id,
            user_name=user.preferred_name if user else None,
            link_method=_value(entrant.link_method),
            badges=[badge.tier.title for badge in held],
            lanyard=lanyard_for(entrant, held, entrant.user_id in set(volunteer_ids)),
            comp_reasons=list(entrant.comp_reasons or []),
            withdrawn_at=entrant.withdrawn_at,
            checked_in_at=entrant.checked_in_at,
            checked_in_by_name=checker.preferred_name if checker else None,
            dm_status=_value(entrant.dm_status),
        )


class CheckInRequest(BaseModel):
    despite_withdrawn: bool = Field(
        default=False,
        description="Staff only: check in someone who no longer holds a badge. Audited.",
    )


class CheckInResultResponse(BaseModel):
    entrant: CheckInEntrantResponse
    already: bool = Field(description="True when someone had already checked them in; nothing changed.")


class LinkEntrantRequest(BaseModel):
    user_id: int


class WalkUpRequest(BaseModel):
    user_id: Optional[int] = Field(default=None, description="An existing member. Give this or `name`.")
    name: Optional[str] = Field(default=None, max_length=255, description="Their name, when they have no account.")
    check_in: bool = Field(default=True, description="Check them in as they're added.")


class CheckInSyncResponse(BaseModel):
    added: int
    updated: int
    withdrawn: int
    rejoined: int
    auto_linked: int
    total: int
    badges: int
    comped: int
