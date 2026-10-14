"""Nav Preference Service — a member's pinned menu items and open menu sections.

The side menu's Pinned block (and, on a phone, the bottom bar) shows the items a
member pinned in this community, and the menu keeps the sections they opened
open from page to page and device to device.

**No audit row and no event**, for the reason ``TablePreferenceService`` gives:
arranging your own menu is not a change to the community's data.

**This service never learns which menu items exist.** Pins are tenant-local
paths, checked for shape only; the menu (presentation) drops a pin the viewer
can no longer reach rather than this service guessing at routes.
"""

from typing import Any, Optional

from application.repositories import NavPreferenceRepository
from application.services.auth_service import AuthService
from application.services.tenant_service import TenantService
from application.tenant_context import require_tenant_id
from models import User

#: Everyone's starting pins: the two Home sections a player keeps coming back to.
DEFAULT_PINS: tuple[str, ...] = ('/home/event', '/home/my-schedule')
#: Added for anyone who can open the admin run sheet.
RUN_SHEET_PIN = '/admin/schedule'


class NavPreferenceService:
    """Read and store one member's side menu arrangement in the current community."""

    MAX_PINS = 12
    MAX_OPEN = 40
    MAX_LEN = 128

    def __init__(self) -> None:
        self.repository = NavPreferenceRepository()

    async def default_pins(self, user: User) -> list[str]:
        pins = list(DEFAULT_PINS)
        if await AuthService.can_view_schedule_board(user):
            pins.append(RUN_SHEET_PIN)
        return pins

    async def load(self, user: Optional[User]) -> tuple[list[str], Optional[list[str]]]:
        """``(pins, open_sections)`` for ``user``; defaults where never edited.

        ``open_sections`` stays ``None`` when the member never opened or closed
        a section, so the menu can pick its own starting state.
        """
        if user is None:
            return [], None
        row = await self.repository.get_for_user(user.id)
        pins = row.pins if row is not None and row.pins is not None else await self.default_pins(user)
        open_sections = row.open_sections if row is not None else None
        return list(pins), (list(open_sections) if open_sections is not None else None)

    async def save_pins(self, user: User, pins: Any) -> list[str]:
        """Store the member's pins, in order. Raises ``ValueError`` on a bad list."""
        clean = self._clean(pins, self.MAX_PINS, path=True)
        await self._ensure_member(user)
        await self.repository.upsert(user.id, pins=clean)
        return clean

    async def save_open_sections(self, user: User, keys: Any) -> list[str]:
        """Store which menu sections the member left open."""
        clean = self._clean(keys, self.MAX_OPEN, path=False)
        await self._ensure_member(user)
        await self.repository.upsert(user.id, open_sections=clean)
        return clean

    async def _ensure_member(self, user: User) -> None:
        tenant_id = require_tenant_id()
        if await AuthService.is_super_admin(user):
            return
        if not await TenantService.is_member(user.id, tenant_id):
            raise ValueError('Join this community to pin items to your menu.')

    def _clean(self, values: Any, limit: int, *, path: bool) -> list[str]:
        if not isinstance(values, (list, tuple)):
            raise ValueError('Menu preferences must be a list.')
        clean: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value or len(value) > self.MAX_LEN:
                raise ValueError('That menu item is not valid.')
            if path and not (value.startswith('/') and not value.startswith('//')):
                raise ValueError('That menu item is not valid.')
            if value not in clean:
                clean.append(value)
        if len(clean) > limit:
            raise ValueError(f'You can pin up to {limit} items.' if path else 'Too many open sections.')
        return clean
