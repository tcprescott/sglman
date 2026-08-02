"""
Match Reschedule Service - Business Logic Layer

Players never move or call off their own matches. They *ask*, and someone who
could already have done it decides — which is the whole point: the alternative
players had was finding a staff member.

Two rules hold the design together.

**Approving performs the change.** ``approve`` calls the existing
``MatchService.update_match`` / ``cancel_match`` rather than writing
``scheduled_at`` itself, so there is exactly one implementation of "move a
match", and the reschedule DM fan-out, acknowledgment reseeding, racetime room
handling and ``match.rescheduled`` event all come with it. A request that were
merely *blessed* would leave staff to go and do the work anyway.

**No new authority.** ``approve`` and ``decline`` gate on ``can_crud_match``,
the same check guarding ``update_match``. Nobody can decide a request who could
not already have made the change by hand.

The opponent's agreement is recorded and never enforced. Staff decide either
way; knowing both players are happy just saves them asking.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from tortoise.exceptions import NoValuesFetched

from application.errors import require_found
from application.events import EventType, match_live
from application.repositories import (
    MatchRepository,
    RescheduleRequestRepository,
    TournamentRepository,
)
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import (
    Match,
    MatchRescheduleRequest,
    RescheduleRequestKind,
    RescheduleRequestStatus,
    User,
)

logger = logging.getLogger(__name__)

REASON_MAX_LENGTH = 500

# States in which there is still something to reschedule. Once a match is
# seated the players are in the room and the answer is a conversation with the
# proctor, not a queue entry staff will read later.
_OPEN_STATES = ('seated_at', 'started_at', 'finished_at', 'confirmed_at')


def _is_override(chosen: Optional[datetime], proposed: Optional[datetime]) -> bool:
    """Did staff approve a *different* time than the one asked for?

    Compared to the minute, the same tolerance ``assert_sg_fields_unchanged``
    uses, because the decision dialog always submits its pickers — which carry
    only ``HH:MM``. Without the tolerance every plain approval would be recorded
    as staff having overridden the player, which is the opposite of what
    happened.
    """
    if chosen is None or proposed is None:
        return False
    return abs((chosen - proposed).total_seconds()) >= 60


class MatchRescheduleService:
    """Player-submitted requests to move or call off a match."""

    def __init__(self) -> None:
        self.repository = RescheduleRequestRepository()
        self.match_repository = MatchRepository()
        self.tournament_repository = TournamentRepository()
        self.audit_service = AuditService()

    # ---- reads ---------------------------------------------------------

    async def get_by_id(self, request_id: int) -> Optional[MatchRescheduleRequest]:
        """Read-only load-or-None for presentation/bot callers."""
        return await self.repository.get_by_id(request_id)

    async def list_pending(
        self,
        actor: Optional[User] = None,
        *,
        tournament_ids: Optional[List[int]] = None,
    ) -> List[MatchRescheduleRequest]:
        """The staff queue for this community.

        Gated, unlike :meth:`list_mine`: a request carries the player's own words
        about why they need the change, which is not schedule data and is nobody
        else's to read. ``actor=None`` is accepted only so an internal caller can
        skip the check deliberately; every entry surface passes one.

        ``tournament_ids`` narrows it the way the admin board narrows itself, so
        a tournament admin is never shown a request they would then be refused
        for deciding.
        """
        if actor is not None:
            await AuthService.ensure(
                await AuthService.can_view_admin(actor),
                "Only staff can read the reschedule queue.",
            )
        return await self.repository.list_pending(tournament_ids=tournament_ids)

    async def list_mine(self, actor: User, limit: int = 25) -> List[MatchRescheduleRequest]:
        """What ``actor`` has asked for, and what became of it.

        No authorization check beyond being the actor: this reads a person's own
        requests and nobody else's. Without it a player who asked a question has
        no way to learn whether anyone answered.
        """
        return await self.repository.list_for_user(actor, limit)

    async def pending_count(self) -> int:
        return await self.repository.pending_count()

    async def pending_match_ids(self) -> List[int]:
        return await self.repository.pending_match_ids()

    async def pending_match_ids_for_user(self, user: User) -> List[int]:
        """Matches where this player already has a request waiting."""
        return await self.repository.pending_match_ids_for_user(user.id)

    async def list_for_match(
        self, match_id: int, actor: Optional[User] = None,
    ) -> List[MatchRescheduleRequest]:
        """Every request raised against one match, newest first.

        Takes an id rather than a ``Match`` so an entry surface never has to load
        the row just to hand it straight back.

        Readable by whoever could decide these, or by a player in the match
        reading about their own. Gated here rather than at the router so every
        surface inherits it.
        """
        if actor is not None:
            match = require_found(
                await self.match_repository.get_by_id(match_id), f"Match {match_id}"
            )
            await AuthService.ensure(
                await AuthService.can_crud_match(actor, match)
                or await self._is_player(match, actor),
                "You can't read the reschedule requests for this match.",
            )
        return await self.repository.list_for_match(match_id)

    # ---- eligibility ---------------------------------------------------

    async def _is_player(self, match: Match, user: User) -> bool:
        """Whether ``user`` plays in ``match``, prefetched or not.

        :meth:`can_request` is called once per row while a board renders, so the
        prefetched roster is used when the caller has one. It falls back to a
        query rather than raising, because a ``Match`` handed in by a page is
        not guaranteed to carry its players and a missing prefetch must not read
        as "not a player" — that would silently hide the control from the very
        people it is for.
        """
        try:
            # Reverse relation and FK id column: mypy cannot see either on a
            # dynamically built Tortoise model.
            players = match.players  # type: ignore[attr-defined]
            return any(p.user_id == user.id for p in players)
        except NoValuesFetched:
            rows = await self.match_repository.get_players(match.id)
            return any(p.user_id == user.id for p in rows)  # type: ignore[attr-defined]

    @staticmethod
    def _blocking_state(match: Match) -> Optional[str]:
        """Why this match can no longer be asked about, or ``None``."""
        if match.scheduled_at is None:
            return "This match doesn't have a time yet, so there's nothing to move."
        for field in _OPEN_STATES:
            if getattr(match, field, None) is not None:
                return "This match is already under way — talk to a proctor."
        return None

    async def can_request(self, match: Match, user: Optional[User]) -> bool:
        """Whether ``user`` may raise a request against ``match``.

        Read by the UI so the control is hidden rather than shown and refused —
        a button that exists only to explain that it does nothing should not be
        there. :meth:`submit` re-checks every clause, because the REST route and
        a forwarded link both reach past whatever the UI decided to render.
        """
        if user is None or not await self._is_player(match, user):
            return False
        if self._blocking_state(match) is not None:
            return False
        if getattr(match, 'speedgaming_episode_id', None) is not None:
            return False
        tournament = await self.tournament_repository.get_by_id(match.tournament_id)  # type: ignore[attr-defined]
        if tournament is None or not getattr(
            tournament, 'allow_reschedule_requests', True
        ):
            return False
        return not await self.repository.get_pending_for(match.id, user.id)

    async def list_requestable_match_ids(self, user: Optional[User]) -> set:
        """Every match ``user`` could raise a request against right now.

        The board's own gate, resolved in three queries rather than
        :meth:`can_request` per row — a schedule with thirty rows would
        otherwise run ninety. Same rules, same order; the per-row method stays
        for the single-match callers (the dialog, the tests).

        The player and match-state clauses are left to the row template, which
        already carries the roster and the state and can decide without a query.
        """
        if user is None:
            return set()
        mine = await self.match_repository.get_upcoming_for_user(user.id)
        already_asked = set(
            await self.repository.pending_match_ids_for_user(user.id)
        )
        return {
            match.id for match in mine
            if match.id not in already_asked
            and getattr(match, 'speedgaming_episode_id', None) is None
            and getattr(match.tournament, 'allow_reschedule_requests', True)
        }

    # ---- the ask -------------------------------------------------------

    async def submit(
        self,
        match_id: int,
        actor: User,
        *,
        reason: str,
        kind: RescheduleRequestKind = RescheduleRequestKind.RESCHEDULE,
        proposed_at: Optional[datetime] = None,
    ) -> MatchRescheduleRequest:
        """Raise a request against a match ``actor`` is playing in."""
        if actor is None:
            raise PermissionError("Login required to ask for a reschedule.")

        match = require_found(
            await self.match_repository.get_by_id(match_id), f"Match {match_id}"
        )
        if not await self._is_player(match, actor):
            raise PermissionError("Only the players in a match can ask for it to be moved.")

        blocking = self._blocking_state(match)
        if blocking:
            raise ValueError(blocking)

        # A sourced match's time belongs to the next sync (``assert_sg_fields_unchanged``),
        # so nobody here could approve this. Refusing now beats a request that
        # sits in the queue until someone discovers it can never be actioned.
        if getattr(match, 'speedgaming_episode_id', None) is not None:
            raise ValueError(
                "This match is synced from SpeedGaming — its time has to change there."
            )

        tournament = require_found(
            await self.tournament_repository.get_by_id(match.tournament_id),  # type: ignore[attr-defined]
            f"Tournament {match.tournament_id}",  # type: ignore[attr-defined]
        )
        if not getattr(tournament, 'allow_reschedule_requests', True):
            raise PermissionError(
                f"{tournament.name} doesn't take reschedule requests here."
            )

        reason = (reason or '').strip()
        if not reason:
            raise ValueError("Say why you need the change — staff decide on the reason.")
        if len(reason) > REASON_MAX_LENGTH:
            raise ValueError(
                f"That reason is a bit long. Keep it under {REASON_MAX_LENGTH} characters."
            )

        if await self.repository.get_pending_for(match_id, actor.id):
            raise ValueError(
                "You already have a request waiting on this match. Withdraw it "
                "first if you want to ask for something different."
            )

        if kind is RescheduleRequestKind.CANCEL:
            # A cancellation proposes no time by definition; accepting one would
            # put a number on the record that nothing ever reads.
            proposed_at = None
        elif proposed_at is not None:
            if proposed_at <= datetime.now(timezone.utc):
                raise ValueError("Pick a time in the future.")
            await self._assert_schedulable(proposed_at, match.tournament_id)  # type: ignore[attr-defined]

        request = await self.repository.create(
            match=match,
            requested_by=actor,
            kind=kind,
            proposed_at=proposed_at,
            reason=reason,
            original_scheduled_at=match.scheduled_at,
        )

        await self.audit_service.write_and_publish(
            actor,
            AuditActions.MATCH_RESCHEDULE_REQUESTED,
            {
                'request_id': request.id,
                'match_id': match_id,
                'kind': kind.value,
                'proposed_at': proposed_at.isoformat() if proposed_at else None,
            },
            EventType.MATCH_RESCHEDULE_REQUESTED,
            event_extra={'tournament_id': match.tournament_id},  # type: ignore[attr-defined]
        )

        # Nudge open views: a staff member already sitting on the schedule board
        # should see the queue strip grow rather than discover the request on
        # their next page load.
        match_live.publish(match_id, match_live.CHANGED)

        await self._notify_submitted(request, match, tournament.name, actor)
        return request

    async def _assert_schedulable(
        self, proposed_at: datetime, tournament_id: int,
    ) -> None:
        """Reject a proposal outside the tournament's operating hours, now.

        The same check ``update_match`` runs at approval. Running it here too is
        the difference between the player being told immediately and staff
        discovering it when they press Approve.
        """
        from application.services.match.match_service import MatchService

        await MatchService().assert_within_tournament_hours(proposed_at, tournament_id)

    # ---- the opponent's signal ----------------------------------------

    async def record_opponent_agreement(
        self, request_id: int, actor: User,
    ) -> MatchRescheduleRequest:
        """The match's *other* player saying the change works for them.

        Advisory. It is stamped on the request and shown to staff, and it gates
        nothing: a request with no agreement is still decidable, and one with
        agreement can still be declined.
        """
        request = require_found(
            await self.repository.get_by_id(request_id), "Reschedule request"
        )
        if request.status is not RescheduleRequestStatus.PENDING:
            raise ValueError("That request has already been decided.")
        if request.requested_by_id == actor.id:  # type: ignore[attr-defined]
            raise PermissionError("You can't agree with your own request.")
        if not await self._is_player(request.match, actor):
            raise PermissionError("Only the other player in the match can agree to this.")

        if request.opponent_agreed_at is None:
            await self.repository.update(
                request, opponent_agreed_at=datetime.now(timezone.utc),
            )
            await self.audit_service.write_and_publish(
                actor,
                AuditActions.MATCH_RESCHEDULE_AGREED,
                {'request_id': request.id, 'match_id': request.match_id},
                EventType.MATCH_RESCHEDULE_AGREED,
                event_extra={'tournament_id': request.match.tournament_id},
            )
            # Agreement changes what staff read on the chip they are about to
            # click, so it earns a nudge even though the queue length is the same.
            match_live.publish(request.match_id, match_live.CHANGED)
        return request

    # ---- the requester taking it back ---------------------------------

    async def withdraw(self, request_id: int, actor: User) -> MatchRescheduleRequest:
        """Take a request back. The requester's alone.

        Distinct from a decline so staff can tell a request they refused from
        one that stopped mattering.
        """
        request = require_found(
            await self.repository.get_by_id(request_id), "Reschedule request"
        )
        if request.requested_by_id != actor.id:  # type: ignore[attr-defined]
            raise PermissionError("Only the person who asked can withdraw a request.")
        if request.status is not RescheduleRequestStatus.PENDING:
            raise ValueError("That request has already been decided.")

        await self.repository.update(
            request,
            status=RescheduleRequestStatus.WITHDRAWN,
            decided_at=datetime.now(timezone.utc),
        )
        await self.audit_service.write_and_publish(
            actor,
            AuditActions.MATCH_RESCHEDULE_WITHDRAWN,
            {'request_id': request.id, 'match_id': request.match_id},  # type: ignore[attr-defined]
            EventType.MATCH_RESCHEDULE_WITHDRAWN,
            event_extra={'tournament_id': request.match.tournament_id},
        )
        # The strip shrinks for the same reason it grew.
        match_live.publish(request.match_id, match_live.CHANGED)  # type: ignore[attr-defined]
        return request

    # ---- the decision --------------------------------------------------

    async def _decidable(self, request_id: int, actor: Optional[User]) -> MatchRescheduleRequest:
        """Load a pending request ``actor`` is allowed to decide."""
        request = require_found(
            await self.repository.get_by_id(request_id), "Reschedule request"
        )
        await AuthService.ensure(
            await AuthService.can_crud_match(actor, request.match),
            "You can't decide reschedule requests for this match.",
        )
        if request.status is not RescheduleRequestStatus.PENDING:
            raise ValueError("That request has already been decided.")
        return request

    async def approve(
        self,
        request_id: int,
        actor: User,
        *,
        scheduled_at: Optional[datetime] = None,
        note: Optional[str] = None,
    ) -> MatchRescheduleRequest:
        """Grant the request, by *making the change*.

        ``scheduled_at`` lets staff counter with a different time than the one
        proposed ("not 14:00, but I can do 20:00"); the requester is told which
        time they got either way.

        Ordering is perform-then-record, so a match that could not actually be
        moved (tournament hours, a SpeedGaming guard) never leaves a request
        marked approved and a schedule that did not budge. The cancellation
        branch has no record step at all: cancelling deletes the match, and the
        request cascades with it, which is why the audit row is written for
        both and is the durable history.
        """
        from application.services.match.match_service import MatchService

        request = await self._decidable(request_id, actor)
        match_id = request.match_id  # type: ignore[attr-defined]
        tournament_id = request.match.tournament_id
        match_service = MatchService()

        superseded: List[int] = []
        if request.kind is RescheduleRequestKind.CANCEL:
            await match_service.cancel_match(
                match_id, actor=actor, reason=note or request.reason,
            )
            final_at = None
        else:
            final_at = scheduled_at or request.proposed_at
            if final_at is None:
                raise ValueError(
                    "This request didn't name a time — pick one before approving it."
                )
            await match_service.update_match(
                match_id, scheduled_at=final_at, actor=actor,
            )
            await self.repository.update(
                request,
                status=RescheduleRequestStatus.APPROVED,
                decided_by=actor,
                decided_at=datetime.now(timezone.utc),
                decision_note=(note or '').strip() or None,
            )
            superseded = await self._supersede_others(request, actor)

        await self.audit_service.write_and_publish(
            actor,
            AuditActions.MATCH_RESCHEDULE_APPROVED,
            {
                'request_id': request_id,
                'match_id': match_id,
                'kind': request.kind.value,
                'scheduled_at': final_at.isoformat() if final_at else None,
                'overrode_proposal': _is_override(scheduled_at, request.proposed_at),
                # The player's own words, and staff's. An approved cancellation
                # deletes the match and the request cascades with it, so without
                # these the audit row is the only record and it would hold
                # neither side of the conversation. ``cancel_match`` records
                # only one of the two, whichever was passed to it.
                'reason': request.reason,
                'note': (note or '').strip() or None,
                # Requests this approval closed out without anyone deciding them.
                'superseded_request_ids': superseded,
            },
            EventType.MATCH_RESCHEDULE_APPROVED,
            event_extra={'tournament_id': tournament_id},
        )

        await self._notify_decided(request, approved=True, new_at=final_at, note=note)
        return request

    async def decline(
        self, request_id: int, actor: User, note: str,
    ) -> MatchRescheduleRequest:
        """Refuse the request, in staff's own words.

        The note is required. A refusal with no reason is the thing this whole
        feature exists to replace.
        """
        request = await self._decidable(request_id, actor)
        note = (note or '').strip()
        if not note:
            raise ValueError('Say why — the note is all the player sees.')

        await self.repository.update(
            request,
            status=RescheduleRequestStatus.DECLINED,
            decided_by=actor,
            decided_at=datetime.now(timezone.utc),
            decision_note=note,
        )
        await self.audit_service.write_and_publish(
            actor,
            AuditActions.MATCH_RESCHEDULE_DECLINED,
            {'request_id': request.id, 'match_id': request.match_id},  # type: ignore[attr-defined]
            EventType.MATCH_RESCHEDULE_DECLINED,
            event_extra={'tournament_id': request.match.tournament_id},
        )
        # Approving reaches ``match_live`` through ``update_match`` /
        # ``cancel_match``; a decline touches no match, so it publishes its own.
        match_live.publish(request.match_id, match_live.CHANGED)  # type: ignore[attr-defined]
        await self._notify_decided(request, approved=False, new_at=None, note=note)
        return request

    async def _supersede_others(
        self, approved: MatchRescheduleRequest, actor: User,
    ) -> List[int]:
        """Close out the match's other open requests once one has settled it.

        Marked ``SUPERSEDED`` rather than declined: staff did not refuse them,
        and a queue entry pointing at a time that has already moved is worse
        than no entry. No DM — everyone involved is a player in the match and
        has just had the reschedule notification. Returns the ids closed, which
        the approval audit records.
        """
        others = [
            r for r in await self.repository.list_pending_for_match(approved.match_id)  # type: ignore[attr-defined]
            if r.id != approved.id
        ]
        for other in others:
            await self.repository.update(
                other,
                status=RescheduleRequestStatus.SUPERSEDED,
                decided_by=actor,
                decided_at=datetime.now(timezone.utc),
            )
        # Returned rather than audited per row: these are a consequence of the
        # one decision, and the approval's own audit entry is where "what did
        # this close?" is answered.
        return [other.id for other in others]

    # ---- notification (best-effort; a DM failure never blocks a decision) --

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
