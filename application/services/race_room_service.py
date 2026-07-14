"""Race Room Service — the racetime room lifecycle for scheduled matches (PR 6).

The business layer that both the auto-open worker and the ``racetimebot/``
handlers call. It maps the racetime room lifecycle onto a :class:`~models.Match`:

    create → open (+ attach seed) → in-progress → finish (capture results) → …
                                                 ↘ cancel

Every transition audits and publishes a ``race_room.*`` domain event, and the
service **acts as the system user** (the racetime room, not a human, is driving
the change). Result capture maps racetime entrants back to linked ``User`` rows,
records place (``finish_rank``) + elapsed time (``finish_time``), handles the
terminal states (forfeit / no-show / DQ / one-finisher), and feeds the existing
result-reporting path (Challonge push is an optional downstream step — a
non-Challonge tournament still closes).

Tenant-scoped: callers run inside ``tenant_scope`` (the worker binds
``match.tenant_id``; the handler binds ``room.tenant_id``; the manual-create UI
runs in the request's tenant). ``manual_create_room`` is the one method gated by
an interactive permission (STAFF / ``SYNC_ADMIN``); the rest are system paths.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from application.events import Event, EventType, event_bus
from application.repositories import RacetimeRoomRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.tenant_context import require_tenant_id
from application.services.user_service import UserService
from models import (
    Match,
    MatchPlayers,
    RaceRoomStatus,
    RacetimeRoom,
    Tournament,
    User,
)
from racetimebot.transport import EntrantStatus, RaceEntrant, RaceRoomEvent

logger = logging.getLogger(__name__)


class RaceRoomService:
    """Drive a racetime room through its lifecycle, mapped onto a ``Match``."""

    def __init__(self) -> None:
        self.room_repository = RacetimeRoomRepository()
        self.audit_service = AuditService()

    # ---- creation / open -------------------------------------------------

    async def create_room_for_match(
        self, match: Match, *, actor: Optional[User] = None, attach_seed: bool = True,
    ) -> RacetimeRoom:
        """Create (or return the existing) racetime room for a match.

        Idempotent — one room per match. Requires the tournament to have an
        authorized racetime bot (its category names the room). Opens the room
        and, when configured, attaches the seed.
        """
        existing = await self.room_repository.get_by_match(match)
        if existing is not None:
            return existing

        tournament = await self._tournament_of(match)
        bot = await tournament.racetime_bot
        if bot is None:
            raise ValueError('This tournament has no racetime bot configured.')

        actor = actor or await self._system_actor()
        now = datetime.now(timezone.utc)
        room = await self.room_repository.create(
            bot_id=bot.id,
            slug=f'{bot.category}/match-{match.id}',
            category=bot.category,
            room_name=(match.title or f'Match {match.id}'),
            status=RaceRoomStatus.OPEN,
            match_id=match.id,
            opened_at=now,
        )
        await self._audit_and_emit(
            actor, room, match, AuditActions.RACE_ROOM_CREATED, EventType.RACE_ROOM_CREATED,
        )
        await self._audit_and_emit(
            actor, room, match, AuditActions.RACE_ROOM_OPENED, EventType.RACE_ROOM_OPENED,
        )
        if attach_seed:
            await self._attach_seed(match, actor)
        return room

    async def manual_create_room(self, actor: Optional[User], match_id: int) -> RacetimeRoom:
        """Create a room on demand (STAFF / SYNC_ADMIN), ignoring the auto toggle."""
        await AuthService.ensure(
            await AuthService.can_manage_sync(actor),
            'You do not have permission to open a racetime room.',
        )
        match = await self._load_match(match_id)
        if match is None:
            raise ValueError('Match not found')
        return await self.create_room_for_match(match, actor=actor)

    # ---- transitions -----------------------------------------------------

    async def mark_in_progress(self, room: RacetimeRoom, *, actor: Optional[User] = None) -> None:
        actor = actor or await self._system_actor()
        now = datetime.now(timezone.utc)
        match = await self._match_of(room)
        if match is not None and match.started_at is None:
            if match.seated_at is None:
                match.seated_at = now
            match.started_at = now
            await match.save()
        await self.room_repository.update(
            room, status=RaceRoomStatus.IN_PROGRESS,
            opened_at=(room.opened_at or now),
        )
        await self._audit_and_emit(
            actor, room, match, AuditActions.RACE_ROOM_STARTED, EventType.RACE_ROOM_STARTED,
        )

    async def cancel_room(
        self, room: RacetimeRoom, *, actor: Optional[User] = None, reason: Optional[str] = None,
    ) -> None:
        actor = actor or await self._system_actor()
        match = await self._match_of(room)
        await self.room_repository.update(room, status=RaceRoomStatus.CANCELLED)
        await self._audit_and_emit(
            actor, room, match, AuditActions.RACE_ROOM_CANCELLED, EventType.RACE_ROOM_CANCELLED,
            extra={'reason': reason} if reason else None,
        )

    async def record_finish(
        self, room: RacetimeRoom, entrants: List[RaceEntrant], *, actor: Optional[User] = None,
    ) -> None:
        """Capture a finished race: map entrants → players, record results, close.

        Handles the terminal states (forfeit / no-show / DQ / one-finisher):
        finishers are placed by racetime's reported place (or elapsed time),
        non-finishers get a null place/time. Entrants whose racetime handle isn't
        linked to a ``User`` are surfaced in the audit detail for staff reconcile.
        """
        actor = actor or await self._system_actor()
        now = datetime.now(timezone.utc)
        match = await self._match_of(room, with_players=True)

        results, unmatched = self._map_results(match, entrants)
        for mp, (rank, ftime) in results.items():
            mp.finish_rank = rank
            mp.finish_time = ftime
            await mp.save()

        if match is not None:
            if match.started_at is None:
                match.started_at = now
            match.finished_at = now
            await match.save()

        await self.room_repository.update(room, status=RaceRoomStatus.FINISHED)

        detail = {
            'ranks': {str(mp.id): rank for mp, (rank, _t) in results.items()},
            'unmatched_handles': unmatched,
        }
        await self._audit_and_emit(
            actor, room, match, AuditActions.RACE_ROOM_FINISHED, EventType.RACE_ROOM_FINISHED,
        )
        await self._audit_and_emit(
            actor, room, match,
            AuditActions.RACE_ROOM_RESULT_RECORDED, EventType.RACE_ROOM_RESULT_RECORDED,
            extra=detail,
        )
        # Feed the existing reporting path so subscribers and downstream systems
        # react exactly as they do for a manually-recorded result.
        if match is not None:
            self._publish_match_result(match, results, actor)
            await self._push_challonge(match, actor)

    # ---- result mapping --------------------------------------------------

    @staticmethod
    def _map_results(
        match: Optional[Match], entrants: List[RaceEntrant],
    ) -> Tuple[Dict[MatchPlayers, Tuple[Optional[int], Optional[int]]], List[str]]:
        """Return ``{MatchPlayers: (finish_rank, finish_time)}`` and unmatched handles."""
        results: Dict[MatchPlayers, Tuple[Optional[int], Optional[int]]] = {}
        unmatched: List[str] = []
        by_rtid: Dict[str, MatchPlayers] = {}
        if match is not None:
            for mp in match.players:
                rtid = getattr(mp.user, 'racetime_user_id', None)
                if rtid:
                    by_rtid[rtid] = mp

        finishers = [
            e for e in entrants
            if e.status == EntrantStatus.DONE and e.finish_time is not None
        ]
        finishers.sort(key=lambda e: (e.place if e.place is not None else e.finish_time))

        seen: set = set()
        for index, entrant in enumerate(finishers, start=1):
            rank = entrant.place if entrant.place is not None else index
            mp = by_rtid.get(entrant.user_id)
            if mp is not None:
                results[mp] = (rank, entrant.finish_time)
                seen.add(entrant.user_id)
            else:
                unmatched.append(entrant.display_name or entrant.user_id)

        for entrant in entrants:
            if entrant.user_id in seen:
                continue
            mp = by_rtid.get(entrant.user_id)
            if mp is not None:
                results[mp] = (None, None)  # forfeit / no-show / DQ
            elif entrant.status != EntrantStatus.DONE:
                unmatched.append(entrant.display_name or entrant.user_id)
        return results, unmatched

    # ---- internals -------------------------------------------------------

    async def _attach_seed(self, match: Match, actor: User) -> None:
        """Roll and attach the tournament's seed (best-effort, non-blocking failure)."""
        tournament = await self._tournament_of(match)
        if not (tournament.preset_id or tournament.seed_generator):
            return
        try:
            from application.services.match_schedule_service import MatchScheduleService

            await MatchScheduleService().generate_seed(match.id, actor)
        except Exception:  # noqa: BLE001 - a seed failure must not block the room
            logger.exception('seed attach failed for match %s', match.id)

    def _publish_match_result(self, match: Match, results, actor: User) -> None:
        from application import match_events

        ranks = {str(mp.id): rank for mp, (rank, _t) in results.items()}
        match_events.publish(match.id)
        event_bus.publish(Event.create(EventType.MATCH_RESULT_RECORDED, {
            'match_id': match.id,
            'tournament_id': match.tournament_id,
            'ranks': ranks,
            'source': 'racetime',
        }, actor))

    async def _push_challonge(self, match: Match, actor: User) -> None:
        try:
            from application.services.challonge_service import ChallongeService

            await ChallongeService().push_result_if_linked(match, actor)
        except Exception:  # noqa: BLE001 - Challonge is an optional downstream step
            logger.exception('challonge push failed for match %s', match.id)

    async def _system_actor(self) -> User:
        return await UserService().get_system_user()

    async def _tournament_of(self, match: Match) -> Tournament:
        tournament = getattr(match, 'tournament', None)
        if isinstance(tournament, Tournament):
            return tournament
        return await Tournament.get(id=match.tournament_id, tenant_id=require_tenant_id())

    async def _match_of(self, room: RacetimeRoom, *, with_players: bool = False) -> Optional[Match]:
        if room.match_id is None:
            return None
        query = Match.get_or_none(id=room.match_id, tenant_id=require_tenant_id())
        if with_players:
            query = query.prefetch_related('players', 'players__user', 'tournament')
        else:
            query = query.prefetch_related('tournament')
        return await query

    async def _load_match(self, match_id: int) -> Optional[Match]:
        return await Match.get_or_none(
            id=match_id, tenant_id=require_tenant_id(),
        ).prefetch_related('tournament', 'players', 'players__user')

    async def _audit_and_emit(
        self, actor: User, room: RacetimeRoom, match: Optional[Match],
        audit_action: str, event_type: str, *, extra: Optional[dict] = None,
    ) -> None:
        detail = {
            'room_id': room.id,
            'slug': room.slug,
            'category': room.category,
            'match_id': room.match_id,
        }
        if match is not None:
            detail['tournament_id'] = match.tournament_id
        if extra:
            detail.update(extra)
        await self.audit_service.write_log(actor, audit_action, detail)
        event_bus.publish(Event.create(event_type, detail, actor))


# Lifecycle adapter the racetimebot/ handler injects: translates a transport
# RaceRoomEvent into the matching RaceRoomService transition. Lives here (not in
# racetimebot/) so the handler stays a thin presentation shim.
class RaceRoomLifecycle:
    """Route a transport room event to the right :class:`RaceRoomService` call."""

    def __init__(self, service: Optional[RaceRoomService] = None) -> None:
        self.service = service or RaceRoomService()

    async def handle_event(self, room: RacetimeRoom, event: RaceRoomEvent) -> None:
        # A room with no match is a qualifier live race (PR 10); route it to the
        # qualifier capture path instead of the match path.
        if room.match_id is None and await self._route_qualifier(room, event):
            return
        if event.status == RaceRoomStatus.IN_PROGRESS:
            await self.service.mark_in_progress(room)
        elif event.status == RaceRoomStatus.FINISHED:
            await self.service.record_finish(room, event.entrants)
        elif event.status == RaceRoomStatus.CANCELLED:
            await self.service.cancel_room(room)
        # OPEN is a no-op: the room already exists in that state.

    async def _route_qualifier(self, room: RacetimeRoom, event: RaceRoomEvent) -> bool:
        """Drive a qualifier live race if the room maps to one; else return False.

        Runs inside the handler's ``tenant_scope(room.tenant_id)`` so the scoped
        by-slug lookup resolves the tenant's own live race.
        """
        from application.services.async_qualifier_live_race_service import (
            AsyncQualifierLiveRaceService,
        )

        service = AsyncQualifierLiveRaceService()
        live_race = await service.repository.get_by_racetime_slug(room.slug)
        if live_race is None:
            return False
        if event.status == RaceRoomStatus.IN_PROGRESS:
            await service.mark_in_progress(live_race)
            await self.service.room_repository.update(room, status=RaceRoomStatus.IN_PROGRESS)
        elif event.status == RaceRoomStatus.FINISHED:
            await service.record_finish(live_race, event.entrants)
            await self.service.room_repository.update(room, status=RaceRoomStatus.FINISHED)
        elif event.status == RaceRoomStatus.CANCELLED:
            await self.service.room_repository.update(room, status=RaceRoomStatus.CANCELLED)
        return True
