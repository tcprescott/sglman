"""
Check-in Desk Service - Business Logic Layer

The desk's reads for callers that arrive without a page gate in front of them:
the REST API and MCP. The desk page itself is behind ``@protected_page``; these
carry the same rule in the service so every other caller gets it too: staff
and Check-in Desk volunteers may read, and a desk volunteer sees only open
events, the ones the desk page offers them.

Kept beside :class:`CheckInService` rather than inside it, which is at its
file-length limit; the desk's writes stay there.
"""

from typing import List, Tuple

from application.errors import NotFoundError, require_found
from application.feature_flags import requires_feature
from application.repositories import CheckInEntrantRepository, CheckInEventRepository
from application.services.auth_service import AuthService
from models import CheckInEntrant, CheckInEvent, CheckInEventStatus, FeatureFlag, User

_DESK_DENIED = 'Only staff and check-in desk volunteers can do that.'


class CheckInDeskService:
    """What the check-in desk reads, gated on who may work it."""

    def __init__(self) -> None:
        self.events = CheckInEventRepository()
        self.entrants = CheckInEntrantRepository()

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def events_for(self, actor: User) -> List[CheckInEvent]:
        """The events this actor can work: every event for staff, open ones for the desk."""
        await AuthService.ensure(await AuthService.can_run_check_in_desk(actor), _DESK_DENIED)
        if await AuthService.can_manage_check_in(actor):
            return await self.events.list_all()
        return await self.events.list_by_status(CheckInEventStatus.OPEN)

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def roster_for(self, actor: User, event_id: int) -> Tuple[CheckInEvent, List[CheckInEntrant]]:
        """An event and its roster, for someone working the desk."""
        await AuthService.ensure(await AuthService.can_run_check_in_desk(actor), _DESK_DENIED)
        event = require_found(await self.events.get_by_id(event_id), 'Check-in event')
        if event.status != CheckInEventStatus.OPEN and not await AuthService.can_manage_check_in(actor):
            raise NotFoundError('Check-in event not found')
        return event, await self.entrants.list_for_event(event)
