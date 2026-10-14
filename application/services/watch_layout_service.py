"""Watch Layout Service — the three Watch page layouts and how viewers rate them.

While the community decides how ``/live`` should look, it offers all three
layouts from the mockups: a viewer lands on a random one (remembered in their
browser), can switch, and can give each a thumbs up or down. Staff read the
tally on Admin → Settings → Watch page.

Anonymous by design: a viewer is their browser (NiceGUI's
``app.storage.browser`` id), since most never sign in. Not audited, for the same
reason page views aren't: it's a reader's opinion, not an action on the event.
"""

import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from application.repositories import WatchLayoutRepository
from application.services.auth_service import AuthService
from models import User

#: Layout key -> the name a viewer sees, in the switcher's order.
WATCH_LAYOUTS: Dict[str, str] = {
    'one_page': 'One page',
    'tabs': 'Tabs',
    'rail': 'Player + rail',
}
VOTES = ('up', 'down')


@dataclass
class LayoutTally:
    layout: str
    label: str
    seen: int = 0
    up: int = 0
    down: int = 0


class WatchLayoutService:
    """Assign, remember and rate Watch page layouts."""

    def __init__(self) -> None:
        self.repository = WatchLayoutRepository()

    @staticmethod
    def resolve(stored: Optional[str]) -> str:
        """The viewer's layout: what their browser remembers, else a random one."""
        if stored in WATCH_LAYOUTS:
            return str(stored)
        return random.choice(list(WATCH_LAYOUTS))

    async def mark_seen(self, session_id: Optional[str], layout: str) -> None:
        if not session_id or layout not in WATCH_LAYOUTS:
            return
        await self.repository.mark_seen(session_id, layout)

    async def votes_for(self, session_id: Optional[str]) -> Dict[str, Optional[str]]:
        if not session_id:
            return {}
        return await self.repository.votes_for(session_id)

    async def vote(self, session_id: Optional[str], layout: str, vote: Optional[str]) -> None:
        """Record ``vote`` ('up', 'down', or None to take it back)."""
        if not session_id:
            raise ValueError('Your browser has no session yet. Reload the page and try again.')
        if layout not in WATCH_LAYOUTS:
            raise ValueError('That layout no longer exists.')
        if vote is not None and vote not in VOTES:
            raise ValueError('A vote is a thumbs up or a thumbs down.')
        await self.repository.set_vote(session_id, layout, vote)

    async def tally(self, actor: Optional[User]) -> List[LayoutTally]:
        """Seen / up / down per layout. Staff only."""
        if actor is None or not await AuthService.is_staff(actor):
            raise PermissionError('Only staff can see the layout votes.')
        out = {key: LayoutTally(key, label) for key, label in WATCH_LAYOUTS.items()}
        for layout, vote in await self.repository.all_rows():
            row = out.get(layout)
            if row is None:
                continue
            row.seen += 1
            if vote == 'up':
                row.up += 1
            elif vote == 'down':
                row.down += 1
        return list(out.values())
