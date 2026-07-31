"""
Crew Service - Business Logic Layer

Handles crew (commentator and tracker) related operations.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Union

from tortoise.transactions import in_transaction

from application.errors import require_found
from application.events import Event, EventType, event_bus, match_live
from application.repositories import CommentatorRepository, MatchRepository, TrackerRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord import discord_queue
from application.services.discord.discord_service import DiscordService
from application.services.tenant_service import TenantService
from application.utils.discord_embeds import COLOR_CANCELLED, COLOR_CREW, notification_embed, time_field
from application.utils.discord_messages import (
    crew_approval_withdrawn_dm,
    crew_assignment_dm,
    crew_withdrawn_dm,
)
from application.utils.match_labels import players_label
from application.utils.timezone import to_utc_aware
from models import Commentator, Tracker, User

logger = logging.getLogger(__name__)


class CrewService:
    """Service for crew-related business operations."""

    def __init__(self) -> None:
        self.commentator_repository = CommentatorRepository()
        self.tracker_repository = TrackerRepository()
        self.match_repository = MatchRepository()
        self.audit_service = AuditService()
        self.discord_service = DiscordService()

    async def signup_crew(
        self,
        match_id: int,
        user: User,
        role: str
    ) -> None:
        """
        Sign up a user as crew (commentator or tracker) for a match.

        Args:
            match_id: Match ID
            user: User signing up
            role: 'commentator' or 'tracker'

        Raises:
            ValueError: If role is invalid or user already signed up
        """
        # Validate role
        if role not in ['commentator', 'tracker']:
            raise ValueError(f"Invalid role: {role}. Must be 'commentator' or 'tracker'")

        # The audit's measured symptom was not that a stranger *saw* a new
        # community's schedule — it was that they were offered Sign Up on it. The
        # page gate stops them reaching the surface, but UI-only gating is not
        # gating: this is reached from the REST API and a Discord button too.
        from application.services.tenant_membership_service import TenantMembershipService
        if not await TenantMembershipService().is_member(user):
            raise ValueError(
                'You are not a member of this community. Ask to join it first.'
            )

        # Get match with crew prefetched
        match = require_found(
            await self.match_repository.get_by_id(match_id, prefetch_relations=True),
            f"Match {match_id}",
        )

        # Crew signup closes once the match is under way. Enforced here (not in a
        # single caller) so the web UI, REST API, and Discord button all honor it.
        # The audit measured signups accepted on matches already in progress, on
        # which "awaiting approval" describes a match that will be over before
        # anyone reads it. Seated-but-not-started stays open on purpose: that is
        # exactly when a stream discovers it still needs a commentator.
        # Withdrawing stays open in either state.
        if match.finished_at is not None:
            raise ValueError("This match has already finished. Crew signup is closed.")
        if match.started_at is not None:
            raise ValueError("This match has already started. Crew signup is closed.")

        # A tournament that requires none of a role does not staff it, and the
        # schedule hides its Sign up control — but UI-only hiding is not a rule,
        # so refuse here too, for the REST route and the Discord button.
        # Withdrawing stays open: a signup from before the setting changed must
        # still be removable.
        required = (
            match.tournament.required_commentators if role == 'commentator'
            else match.tournament.required_trackers
        ) if match.tournament else 1
        if required == 0:
            raise ValueError(f"This tournament does not use {role}s.")

        # Check if user already signed up
        crew_list = match.commentators if role == 'commentator' else match.trackers
        if any(c.user_id == user.id for c in crew_list):
            raise ValueError(f"User already signed up as {role}")

        players = await self.match_repository.get_players(match)
        if any(p.user_id == user.id for p in players):
            raise ValueError("Players cannot sign up as crew for their own match")

        # Create crew entry (not approved by default)
        if role == 'commentator':
            await self.commentator_repository.create(match=match, user=user, approved=False)
        else:
            await self.tracker_repository.create(match=match, user=user, approved=False)

        await self.audit_service.write_and_publish(
            user,
            AuditActions.CREW_SIGNUP_CREATED,
            {'match_id': match_id, 'role': role},
            EventType.CREW_SIGNUP_CREATED,
            event_extra={'user_id': user.id},
        )
        match_live.publish(match_id)

    async def undo_crew_signup(
        self,
        match_id: int,
        user: User,
        role: str
    ) -> None:
        """
        Remove a user's crew signup (commentator or tracker) from a match.

        Args:
            match_id: Match ID
            user: User to remove
            role: 'commentator' or 'tracker'

        Raises:
            ValueError: If role is invalid or user not signed up
        """
        # Validate role
        if role not in ['commentator', 'tracker']:
            raise ValueError(f"Invalid role: {role}. Must be 'commentator' or 'tracker'")

        # The audit's measured symptom was not that a stranger *saw* a new
        # community's schedule — it was that they were offered Sign Up on it. The
        # page gate stops them reaching the surface, but UI-only gating is not
        # gating: this is reached from the REST API and a Discord button too.
        from application.services.tenant_membership_service import TenantMembershipService
        if not await TenantMembershipService().is_member(user):
            raise ValueError(
                'You are not a member of this community. Ask to join it first.'
            )

        # Get match with crew prefetched
        match = require_found(
            await self.match_repository.get_by_id(match_id, prefetch_relations=True),
            f"Match {match_id}",
        )

        # Find crew member
        crew_list = match.commentators if role == 'commentator' else match.trackers
        crew_member = next((c for c in crew_list if c.user_id == user.id), None)

        if not crew_member:
            raise ValueError(f"User is not signed up as {role}")

        # Read before the delete: the row is the only place the approver is
        # recorded, and the notification below needs it.
        was_approved = bool(crew_member.approved)
        approved_by_id = crew_member.approved_by_id

        # Delete crew entry
        await crew_member.delete()

        await self.audit_service.write_and_publish(
            user,
            AuditActions.CREW_SIGNUP_REMOVED,
            {'match_id': match_id, 'role': role, 'was_approved': was_approved},
            EventType.CREW_SIGNUP_REMOVED,
            event_extra={'user_id': user.id},
        )
        match_live.publish(match_id)

        if was_approved:
            await self._notify_crew_withdrawal(match, user, role, approved_by_id)

    async def get_crew_member_by_id(
        self,
        crew_id: int,
        crew_type: str,
    ) -> Optional[Union[Commentator, Tracker]]:
        if crew_type == 'commentator':
            return await self.commentator_repository.get_by_id(crew_id)
        elif crew_type == 'tracker':
            return await self.tracker_repository.get_by_id(crew_id)
        else:
            raise ValueError(f"Invalid crew_type: {crew_type}. Must be 'commentator' or 'tracker'")

    async def update_crew_approval(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
        approved: bool,
        actor: Optional[User] = None,
    ) -> Union[Commentator, Tracker]:
        if crew_type not in ('commentator', 'tracker'):
            raise ValueError(f"Invalid crew_type: {crew_type}. Must be 'commentator' or 'tracker'")

        await crew_member.fetch_related('match', 'user', 'match__stream_room')
        await AuthService.ensure(
            await AuthService.can_approve_crew(actor, crew_member.match),
            f"User cannot approve {crew_type} signups for match {crew_member.match.id}",
        )

        # Refresh from DB to narrow the race window where two admins approve concurrently.
        await crew_member.refresh_from_db()
        was_approved = bool(crew_member.approved)
        was_acknowledged = crew_member.acknowledged_at is not None

        # No-op if state already matches — don't audit or DM for a click that didn't change anything.
        if was_approved == approved:
            return crew_member

        crew_member.approved = approved
        crew_member.approved_by = actor if approved else None
        if not approved:
            crew_member.acknowledged_at = None

        async with in_transaction():
            await crew_member.save()
            details = {
                'crew_type': crew_type,
                'crew_id': crew_member.id,
                'match_id': crew_member.match.id,
                'approved': approved,
            }
            if not approved and was_acknowledged:
                details['previously_acknowledged'] = True
            await self.audit_service.write_log(
                actor,
                AuditActions.CREW_APPROVAL_CHANGED,
                details,
            )

        if approved:
            await self._request_crew_acknowledgment(crew_member, crew_type)
        else:
            await self._notify_crew_approval_withdrawn(crew_member, crew_type)

        match_live.publish(crew_member.match.id)
        event_bus.publish(Event.create(EventType.CREW_APPROVAL_CHANGED, {
            'match_id': crew_member.match.id, 'crew_type': crew_type,
            'user_id': crew_member.user_id, 'approved': approved,
        }, actor))

        return crew_member

    async def approve_crew_member(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
        actor: Optional[User] = None,
    ) -> Union[Commentator, Tracker]:
        return await self.update_crew_approval(crew_member, crew_type, approved=True, actor=actor)

    async def acknowledge_crew_assignment(
        self,
        crew_id: int,
        crew_type: str,
        user: User,
    ) -> Union[Commentator, Tracker]:
        """Mark a crew assignment as acknowledged by the crew member themselves.

        Only the assigned crew member may acknowledge their own assignment, and
        only after an admin has approved it. Already-acknowledged assignments
        are treated as a no-op so double-clicks don't surface confusing errors.
        """
        crew_member = require_found(
            await self.get_crew_member_by_id(crew_id, crew_type),
            f"{crew_type.capitalize()} assignment",
        )

        await crew_member.fetch_related('user', 'match')

        if crew_member.user_id != user.id:
            raise ValueError("You can only acknowledge your own crew assignments.")

        if not crew_member.approved:
            raise ValueError(
                f"This {crew_type} assignment has not been approved yet."
            )

        if crew_member.acknowledged_at is not None:
            return crew_member

        async with in_transaction():
            if crew_type == 'commentator':
                crew_member = await self.commentator_repository.acknowledge(crew_member)
            else:
                crew_member = await self.tracker_repository.acknowledge(crew_member)

            await self.audit_service.write_log(
                user,
                AuditActions.CREW_ACKNOWLEDGED,
                {
                    'crew_type': crew_type,
                    'crew_id': crew_member.id,
                    'match_id': crew_member.match_id,
                },
            )

        match_live.publish(crew_member.match_id)
        event_bus.publish(Event.create(EventType.CREW_ACKNOWLEDGED, {
            'match_id': crew_member.match_id, 'crew_type': crew_type,
            'user_id': user.id,
        }, user))

        return crew_member

    async def _crew_dm_parts(self, match):
        """Shared DM ingredients for every crew notification.

        Returns the message-builder kwargs and the embed field list — all three
        notifications describe the same assignment, so they identify it from the
        same fields.
        """
        players = await match.players.all().prefetch_related('user')
        player_names = [p.user.preferred_name for p in players] if players else []
        message_kwargs = {
            'match_title': match.title or None,
            'scheduled_at_display': time_field(match.scheduled_at),
            'stream_room_name': match.stream_room.name if match.stream_room else None,
            'player_names': player_names or None,
        }

        players_str = players_label(player_names)
        fields = [('Match', match.title or players_str, False)]
        if match.title and players_str:
            fields.append(('Players', players_str, True))
        fields.append(('Time', time_field(match.scheduled_at), False))
        if match.stream_room:
            fields.append(('Stage', match.stream_room.name, True))
        return message_kwargs, fields

    async def _request_crew_acknowledgment(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
    ) -> None:
        """Send a Discord DM asking the crew member to confirm their assignment.

        Best-effort: failures (DMs disabled, user not on Discord, bot offline,
        Discord library errors) are logged but never raise. The web
        acknowledgment button remains available regardless of DM delivery.
        """
        discord_id = getattr(crew_member.user, 'discord_id', None)
        if not discord_id:
            return

        message_kwargs, fields = await self._crew_dm_parts(crew_member.match)
        message = crew_assignment_dm(crew_type=crew_type, **message_kwargs)
        embed = notification_embed(
            title=f'🎙️ {crew_type.capitalize()} assignment',
            color=COLOR_CREW,
            community_name=await TenantService.current_community_name(),
            description='Tap **Acknowledge** below to confirm you can cover this.',
            fields=fields,
        )

        discord_queue.enqueue(
            self.discord_service.send_dm_with_crew_acknowledgment_button(
                int(discord_id), message, crew_type, crew_member.id, embed=embed,
            )
        )

    async def _notify_crew_approval_withdrawn(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
    ) -> None:
        """Tell a crew member their approval was withdrawn.

        The counterpart to :meth:`_request_crew_acknowledgment`: withdrawing also
        clears any acknowledgment, so without this the person who confirmed they
        would cover a match is silently dropped from it. Best-effort on the same
        terms — a failed DM never blocks the withdrawal.
        """
        discord_id = getattr(crew_member.user, 'discord_id', None)
        if not discord_id:
            return

        message_kwargs, fields = await self._crew_dm_parts(crew_member.match)
        message = crew_approval_withdrawn_dm(crew_type=crew_type, **message_kwargs)
        embed = notification_embed(
            title=f'🎙️ {crew_type.capitalize()} assignment withdrawn',
            color=COLOR_CANCELLED,
            community_name=await TenantService.current_community_name(),
            description="You're no longer on the crew for this match.",
            fields=fields,
        )

        discord_queue.enqueue(
            self.discord_service.send_dm(int(discord_id), message, embed=embed)
        )

    async def _notify_crew_withdrawal(
        self,
        match,
        volunteer: User,
        crew_type: str,
        approved_by_id: Optional[int],
    ) -> None:
        """Tell whoever owns this match's crew that an approved member dropped it.

        The mirror of :meth:`_notify_crew_approval_withdrawn`, and the shape
        ``VolunteerScheduleService._notify_coordinators_of_release`` established:
        a schedule still showing someone who has already gone is worse than one
        showing an open slot, so the people who can fill it are told.

        Only for an *approved* signup. An unapproved one was never announced to
        anybody, so its removal has nothing to correct — the same reason a
        cleared volunteer draft stays silent.

        Best-effort: a failed DM never blocks the withdrawal.
        """
        from application.repositories import TournamentRepository

        recipients: dict[int, User] = {}
        if match.tournament_id:
            for owner in await TournamentRepository.get_crew_owners(match.tournament_id):
                recipients[owner.id] = owner
        if approved_by_id and approved_by_id not in recipients:
            # The approver is the one person who acted on this signup, and may be
            # community STAFF rather than one of the tournament's own people.
            approver = await User.get_or_none(id=approved_by_id)
            if approver:
                recipients[approver.id] = approver
        recipients.pop(volunteer.id, None)
        if not recipients:
            return

        message_kwargs, fields = await self._crew_dm_parts(match)
        hours_notice = None
        if match.scheduled_at:
            hours_notice = round(
                (to_utc_aware(match.scheduled_at) - datetime.now(timezone.utc)).total_seconds()
                / 3600.0,
                1,
            )
        message = crew_withdrawn_dm(
            crew_type=crew_type,
            volunteer_name=volunteer.preferred_name,
            hours_notice=hours_notice,
            **message_kwargs,
        )
        embed = notification_embed(
            title=f'🎙️ {crew_type.capitalize()} withdrew',
            color=COLOR_CANCELLED,
            community_name=await TenantService.current_community_name(),
            description=f'**{volunteer.preferred_name}** is no longer covering this '
                        f'as {crew_type}. The slot is open again.',
            fields=fields,
        )

        for recipient in recipients.values():
            discord_id = getattr(recipient, 'discord_id', None)
            if not discord_id or not getattr(recipient, 'dm_notifications', True):
                continue
            discord_queue.enqueue(
                self.discord_service.send_dm(int(discord_id), message, embed=embed)
            )
