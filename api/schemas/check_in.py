"""Schemas for the check-in desk endpoints."""

from datetime import datetime
from typing import Iterable, List, Optional

from pydantic import BaseModel, Field

from application.services.check_in_rules import active_badges, lanyard_for
from models import CheckInEntrant, CheckInEvent


def _value(enum_or_none) -> Optional[str]:
    return getattr(enum_or_none, 'value', enum_or_none)


class CheckInEventResponse(BaseModel):
    id: int = Field(..., description="Check-in event id.")
    name: str = Field(..., description="Event name.")
    status: str = Field(..., description="`draft`, `open` or `closed`. Only open events are synced automatically and shown to Check-in desk volunteers.")
    matcherino_venue_id: Optional[int] = Field(None, description="The Matcherino venue badges are sold under; empty for an event that only comps people.")
    last_synced_at: Optional[datetime] = Field(None, description="When the roster last synced (UTC).")
    last_sync_error: Optional[str] = Field(None, description="Why the last sync failed; empty when it succeeded.")
    last_sync_count: Optional[int] = Field(None, description="How many people the last sync covered.")

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
    id: int = Field(..., description="Roster entry id.")
    event_id: int = Field(..., description="The check-in event this row is on.")
    display_name: str = Field(..., description="The name the desk shows.")
    source: str = Field(description="`matcherino`, `walk_up` or `comp`.")
    user_id: Optional[int] = Field(None, description="The linked member account; empty when no account is linked.")
    user_name: Optional[str] = Field(None, description="The linked member's display name.")
    link_method: Optional[str] = Field(None, description="How the account was linked: `matcherino_id`, `discord_id`, `twitch_id`, `matcherino_handle`, `manual`, `walk_up` or `comp`. `manual` with no account means someone unlinked it by hand.")
    badges: List[str] = Field(
        default_factory=list,
        description="Badge types they still hold, most expensive first. Empty for a walk-up or a comp.",
    )
    lanyard: Optional[str] = Field(
        default=None,
        description="The lanyard the desk hands over (`staff`, `volunteer`, or a badge type's), or null.",
    )
    comp_reasons: List[str] = Field(default_factory=list, description="Why the person is comped: role names and `volunteer`. Empty when they aren't comped.")
    withdrawn_at: Optional[datetime] = Field(
        default=None,
        description="Set when they no longer hold a badge. Only staff can check them in anyway.",
    )
    checked_in_at: Optional[datetime] = Field(None, description="When they were checked in (UTC); empty if they haven't been.")
    checked_in_by_name: Optional[str] = Field(None, description="Who checked them in.")
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
    entrant: CheckInEntrantResponse = Field(..., description="The roster row after the check-in.")
    already: bool = Field(description="True when someone had already checked them in; nothing changed.")


class LinkEntrantRequest(BaseModel):
    user_id: int = Field(..., description="The member account to link. Must be an active member of this community.")


class WalkUpRequest(BaseModel):
    user_id: Optional[int] = Field(default=None, description="An existing member. Give this or `name`.")
    name: Optional[str] = Field(default=None, max_length=255, description="Their name, when they have no account.")
    check_in: bool = Field(default=True, description="Check them in as they're added.")


class CheckInSyncResponse(BaseModel):
    added: int = Field(..., description="People added to the roster.")
    updated: int = Field(..., description="Existing rows whose badges or details changed.")
    withdrawn: int = Field(..., description="People marked withdrawn because they no longer hold a badge or a comp.")
    rejoined: int = Field(..., description="Previously withdrawn people who hold a badge or comp again.")
    auto_linked: int = Field(..., description="Rows matched to a member account automatically.")
    total: int = Field(..., description="Buyers who currently hold at least one badge.")
    badges: int = Field(..., description="Active (unrefunded) badges in the sales.")
    comped: int = Field(..., description="Members the comp rules cover.")
