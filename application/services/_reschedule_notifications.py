"""Reschedule-request notifications: who is told a request exists, and how it went.

Split out of ``match_reschedule_service`` as pure code motion when that module
approached the file-length budget, following the ``_schedule_notifications``
convention next door: :class:`RescheduleNotificationMixin` is composed into
:class:`MatchRescheduleService` and reaches its sibling helpers through that one
composed class, so every caller keeps using the service unchanged.

Every method here is best-effort — a DM failure is logged and swallowed, because
a request that was submitted or decided stays submitted or decided whether or
not Discord took the message.

Two audience rules live here rather than at the call sites. The deciders are
STAFF ∪ the tournament's own admins, because ``_decidable`` gates on
``can_crud_match`` and DMing only STAFF left a TA-run tournament with nobody
told. And an approval that *moved* the match sends nothing back: ``update_match``
has already fanned the reschedule out to both players.
"""

import logging
from datetime import datetime
from typing import Optional, Sequence

from models import Match, MatchRescheduleRequest, RescheduleRequestKind, User

logger = logging.getLogger(__name__)


class RescheduleNotificationMixin:
    """The DM fan-out for a request's submission and its decision."""

    async def _notify_submitted(
        self,
        request: MatchRescheduleRequest,
        match: Match,
        tournament_name: str,
        requester: User,
    ) -> None:
        """Tell staff there is something to decide, and the opponent it was asked."""
        try:
            await self._send_submitted(request, match, tournament_name, requester)
        except Exception:
            logger.exception('reschedule request notification failed for %s', request.id)

    async def _send_submitted(
        self,
        request: MatchRescheduleRequest,
        match: Match,
        tournament_name: str,
        requester: User,
    ) -> None:
        from application.services import notification_links
        from application.services.discord import DiscordService, discord_queue
        from application.services.tenant_service import TenantService
        from application.utils.discord_embeds import (
            COLOR_RESCHEDULED,
            notification_embed,
            time_field,
        )
        from application.utils.discord_messages_reschedule import (
            reschedule_opponent_dm,
            reschedule_requested_dm,
        )

        community = await TenantService.current_community_name()
        cancel = request.kind is RescheduleRequestKind.CANCEL
        current_display = time_field(match.scheduled_at)
        proposed_display = time_field(request.proposed_at)
        names = [p.user.preferred_name for p in match.players]  # type: ignore[attr-defined]
        service = DiscordService()

        staff_body = reschedule_requested_dm(
            tournament_name, requester.preferred_name,
            kind_cancel=cancel, current_display=current_display,
            proposed_display=proposed_display, reason=request.reason,
            player_names=names,
        )
        staff_embed = notification_embed(
            title='🔁 Reschedule request',
            color=COLOR_RESCHEDULED,
            community_name=community,
            description=staff_body,
        )
        # The decision dialog itself, not the board: the reason and the proposed
        # time are the whole message and they live in the dialog.
        staff_link = await notification_links.admin_reschedule_request(request.id)
        for member in await self._deciders(match):
            if member.discord_id:
                discord_queue.enqueue(service.send_dm(
                    int(member.discord_id), staff_body,
                    embed=staff_embed, link=staff_link,
                ))

        opponents = self._opponents(match, requester)
        # One column records agreement, so it can only mean "the other player".
        # A match with more than two players skips the signal entirely rather
        # than recording one person's yes as if it were everyone's.
        if len(opponents) != 1:
            return
        opponent = opponents[0]
        if not opponent.discord_id:
            return
        opponent_body = reschedule_opponent_dm(
            tournament_name, requester.preferred_name,
            kind_cancel=cancel, current_display=current_display,
            proposed_display=proposed_display, reason=request.reason,
        )
        opponent_embed = notification_embed(
            title='🔁 Your opponent asked to reschedule',
            color=COLOR_RESCHEDULED,
            community_name=community,
            description=opponent_body,
        )
        discord_queue.enqueue(service.send_dm_with_reschedule_agree_button(
            int(opponent.discord_id), opponent_body, request.id,
            embed=opponent_embed,
            link=await notification_links.player_matches(),
        ))

    @staticmethod
    async def _deciders(match: Match) -> Sequence[User]:
        """Everyone who could actually answer this: STAFF ∪ the tournament's admins.

        ``_decidable`` gates on ``can_crud_match``, which admits the tournament's
        own admin as well as global staff. DMing only STAFF meant that in a
        community where a tournament is run by a TA, nobody who owns it was told
        a request existed — it surfaced only if someone happened to open the
        board.
        """
        from application.repositories import UserRoleRepository
        from models import Role

        recipients = {
            member.id: member
            for member in await UserRoleRepository.list_users_with_role(Role.STAFF)
        }
        await match.fetch_related('tournament__admins')
        for admin in match.tournament.admins:
            recipients.setdefault(admin.id, admin)
        return list(recipients.values())

    @staticmethod
    def _opponents(match: Match, requester: User) -> Sequence[User]:
        players = match.players  # type: ignore[attr-defined]
        return [p.user for p in players if p.user_id != requester.id]

    async def _notify_decided(
        self,
        request: MatchRescheduleRequest,
        *,
        approved: bool,
        new_at: Optional[datetime],
        note: Optional[str],
    ) -> None:
        try:
            await self._send_decided(request, approved=approved, new_at=new_at, note=note)
        except Exception:
            logger.exception('reschedule decision notification failed for %s', request.id)

    async def _send_decided(
        self,
        request: MatchRescheduleRequest,
        *,
        approved: bool,
        new_at: Optional[datetime],
        note: Optional[str],
    ) -> None:
        """DM the requester the outcome.

        An approval that *moved* the match sends nothing: ``update_match`` has
        already fanned the reschedule notification out to both players and the
        crew, and a second "your request was approved" would be the same news
        twice. A decline is the one outcome no other notification covers, and
        an approved cancellation is worth confirming because the match DM says
        only that it was called off, not that they were the reason.
        """
        from application.services import notification_links
        from application.services.discord import DiscordService, discord_queue
        from application.services.tenant_service import TenantService
        from application.utils.discord_embeds import (
            COLOR_CANCELLED,
            COLOR_RESCHEDULED,
            notification_embed,
            time_field,
        )
        from application.utils.discord_messages_reschedule import reschedule_decided_dm

        cancel = request.kind is RescheduleRequestKind.CANCEL
        if approved and not cancel:
            return

        requester = request.requested_by
        if not requester.discord_id:
            return

        community = await TenantService.current_community_name()
        tournament_name = request.match.tournament.name
        body = reschedule_decided_dm(
            tournament_name, approved=approved, kind_cancel=cancel,
            new_display=time_field(new_at), note=(note or '').strip(),
        )
        embed = notification_embed(
            title='🔁 Reschedule request ' + ('approved' if approved else 'declined'),
            color=COLOR_RESCHEDULED if approved else COLOR_CANCELLED,
            community_name=community,
            description=body,
        )
        # Only a decline gets a button. "Ask again with a different time" is a
        # real next step; an approval has nothing left for them to press.
        link = (
            None if approved
            else await notification_links.player_reschedule(request.match_id)  # type: ignore[attr-defined]
        )
        discord_queue.enqueue(
            DiscordService().send_dm(
                int(requester.discord_id), body, embed=embed, link=link,
            )
        )
