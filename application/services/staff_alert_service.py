"""Who hears about a match alert: the admin on duty and the tournament's admins.

A *match alert* is a staff-facing DM about one match that somebody has to pick
up: a player's comment, a reschedule request. It used to go to every STAFF
member at once, so during an event a dozen people were pinged for each one.

Now it goes to

* whoever holds a published shift, right now, on a volunteer position with
  ``staff_alerts`` on (sgl26's Admin Desk), and
* the tournament's admins, minus any who switched alerts off for it.

If nobody is on such a shift (a community that never set the switch, or a gap
in the roster) the alert falls back to every STAFF member, so it is never lost.
Community-wide requests (join, ADA, community events) are not match alerts and
still go to all staff.
"""

from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, Iterable, List, Optional

from application.errors import require_found
from application.repositories import (
    TournamentNotificationRepository,
    TournamentRepository,
    UserRoleRepository,
    VolunteerAssignmentRepository,
)
from application.services.auth_service import AuthService
from models import Match, Role, Tournament, User

#: May this person act on the alert? A DM that links somewhere the reader
#: cannot act is worse than none, so recipients are filtered by it.
CanAct = Callable[[User, Match], Awaitable[bool]]


class StaffAlertService:
    """Resolve match-alert recipients and a tournament admin's opt-out."""

    @staticmethod
    async def on_duty_now(at: Optional[datetime] = None) -> List[User]:
        """Who is on an alert-receiving shift at ``at`` (default: now)."""
        return await VolunteerAssignmentRepository.on_duty_users(at or datetime.now(timezone.utc))

    @staticmethod
    async def match_alert_recipients(
        match: Match,
        *,
        can_act: CanAct = AuthService.can_run_match,
        exclude: Iterable[int] = (),
        at: Optional[datetime] = None,
    ) -> List[User]:
        """The on-duty admins plus the tournament's opted-in admins.

        ``exclude`` drops user ids (the comment's author, the requester).
        Falls back to every STAFF member when nobody who can act is on duty.
        """
        skip = set(exclude)
        recipients: Dict[int, User] = {}

        async def add(user: User) -> None:
            if user.id in skip or user.id in recipients or not user.is_active:
                return
            if await can_act(user, match):
                recipients[user.id] = user

        for user in await StaffAlertService.on_duty_now(at):
            await add(user)
        if not recipients:
            for user in await UserRoleRepository.list_users_with_role(Role.STAFF):
                await add(user)

        await match.fetch_related('tournament__admins')
        tournament = match.tournament
        if tournament is not None:
            opted_out = await TournamentNotificationRepository().staff_alert_opt_out_user_ids(tournament.id)
            for admin in tournament.admins:
                if admin.id not in opted_out:
                    await add(admin)
        return list(recipients.values())

    @staticmethod
    async def admin_tournaments(user: User) -> List[tuple[Tournament, bool]]:
        """The active tournaments ``user`` admins, each with whether alerts are on."""
        tournaments = await TournamentRepository.active_admin_tournaments(user)
        if not tournaments:
            return []
        prefs = {
            p.tournament_id: p.staff_alerts  # type: ignore[attr-defined]
            for p in await TournamentNotificationRepository().get_all_for_user(user)
        }
        return [(t, prefs.get(t.id, True)) for t in tournaments]

    @staticmethod
    async def set_tournament_alerts(user: User, tournament_id: int, on: bool) -> None:
        """Switch one tournament's match alerts on or off for one of its admins."""
        tournament = require_found(
            await TournamentRepository().get_by_id(tournament_id), f'Tournament {tournament_id}',
        )
        if not await AuthService.is_tournament_admin(user, tournament.id):
            raise ValueError("You only get alerts for tournaments you run.")
        await TournamentNotificationRepository().set_staff_alerts(user, tournament, on)
