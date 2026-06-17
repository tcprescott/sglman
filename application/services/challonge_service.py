"""
Challonge Service - Business Logic Layer

Coordinates the Challonge integration: the SGL service-account OAuth
connection, per-player identity linking, pulling a tournament's bracket into
sglman, scheduling bracket matchups (via the existing match-request flow), and
pushing results back to Challonge.

Credential model: one shared SGL service account writes brackets. Players link
their own Challonge identity (scope ``me``) only so we can map them to bracket
participants; their tokens are not retained.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from application.repositories import ChallongeRepository, TournamentRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.match_service import MatchService
from application.utils.challonge_client import (
    ChallongeAPIError,
    ChallongeClient,
    MockChallongeClient,
    build_authorize_url,
)
from application.utils.mock_challonge import is_mock_challonge
from models import (
    ChallongeConnection,
    ChallongeMatch,
    ChallongeMatchState,
    Match,
    Tournament,
    User,
)

# Refresh the service token slightly before it actually expires.
_TOKEN_REFRESH_BUFFER = timedelta(minutes=5)

# Collapse rapid repeat syncs (double-clicks, webhook bursts) — a non-forced
# sync within this window of the last one is treated as a no-op.
_SYNC_THROTTLE_WINDOW = timedelta(seconds=60)

# The Challonge plan's monthly request quota, surfaced in the admin UI.
CHALLONGE_MONTHLY_QUOTA = 500

_DEFAULT_SERVICE_SCOPES = 'me tournaments:read matches:read matches:write participants:read'
_PLAYER_SCOPES = 'me'


def _base_url() -> str:
    return os.getenv('BASE_URL', 'http://localhost:8000').rstrip('/')


def _redirect_uri() -> str:
    # One registered redirect URI serves both the service-account and the
    # per-player flows; Challonge OAuth apps only validate against a single URI.
    return os.getenv('CHALLONGE_REDIRECT_URI') or f"{_base_url()}/challonge/oauth/callback"


def _service_scopes() -> str:
    return os.getenv('CHALLONGE_SCOPES') or _DEFAULT_SERVICE_SCOPES


def _as_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Treat naive datetimes (e.g. from a non-tz DB) as UTC so comparisons are safe."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class ChallongeService:
    """Business logic for the Challonge integration."""

    def __init__(self):
        self.repository = ChallongeRepository()
        self.tournament_repository = TournamentRepository()
        self.audit_service = AuditService()

    # ------------------------------------------------------------------
    # OAuth configuration / URLs (reused by the OAuth middleware)
    # ------------------------------------------------------------------
    @staticmethod
    def is_configured() -> bool:
        """True when the OAuth app credentials are present (or mock is on)."""
        if is_mock_challonge():
            return True
        return bool(os.getenv('CHALLONGE_CLIENT_ID') and os.getenv('CHALLONGE_CLIENT_SECRET'))

    @staticmethod
    def service_authorize_url(state: str) -> str:
        return build_authorize_url(
            os.getenv('CHALLONGE_CLIENT_ID', ''), _redirect_uri(), _service_scopes(), state,
        )

    @staticmethod
    def player_authorize_url(state: str) -> str:
        return build_authorize_url(
            os.getenv('CHALLONGE_CLIENT_ID', ''), _redirect_uri(), _PLAYER_SCOPES, state,
        )

    @staticmethod
    def redirect_uri() -> str:
        return _redirect_uri()

    # ------------------------------------------------------------------
    # Client factories
    # ------------------------------------------------------------------
    def _oauth_client(self) -> ChallongeClient:
        """Client for token exchange/refresh and get_me (no bearer needed)."""
        cls = MockChallongeClient if is_mock_challonge() else ChallongeClient
        return cls(
            client_id=os.getenv('CHALLONGE_CLIENT_ID', ''),
            client_secret=os.getenv('CHALLONGE_CLIENT_SECRET', ''),
            on_request=self.repository.increment_api_usage,
        )

    def _api_client(self) -> ChallongeClient:
        """Client for authenticated service calls (token via get_valid_access_token)."""
        cls = MockChallongeClient if is_mock_challonge() else ChallongeClient
        return cls(
            client_id=os.getenv('CHALLONGE_CLIENT_ID', ''),
            client_secret=os.getenv('CHALLONGE_CLIENT_SECRET', ''),
            token_provider=self.get_valid_access_token,
            on_request=self.repository.increment_api_usage,
        )

    # ------------------------------------------------------------------
    # Service-account token management
    # ------------------------------------------------------------------
    async def get_valid_access_token(self, force_refresh: bool = False) -> str:
        """Return a live service access token, refreshing if expired/forced."""
        connection = await self.repository.get_connection()
        if connection is None:
            raise ValueError("Challonge is not connected. A staff member must connect the SGL account.")

        if not force_refresh and not self._token_expiring(connection):
            return connection.access_token

        if not connection.refresh_token:
            if force_refresh:
                raise ValueError("Challonge token expired and no refresh token is available; reconnect required.")
            return connection.access_token

        payload = await self._oauth_client().refresh(connection.refresh_token)
        access, refresh, expires_at = self._unpack_token(payload)
        await self.repository.update_connection_tokens(connection, access, refresh, expires_at)
        return access

    @staticmethod
    def _token_expiring(connection: ChallongeConnection) -> bool:
        if connection.token_expires_at is None:
            return False
        expires = _as_aware_utc(connection.token_expires_at)
        return datetime.now(timezone.utc) >= (expires - _TOKEN_REFRESH_BUFFER)

    @staticmethod
    def _unpack_token(payload: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[datetime]]:
        access = payload.get('access_token')
        if not access:
            raise ChallongeAPIError(f"Challonge token response missing access_token: {payload}")
        refresh = payload.get('refresh_token')
        expires_in = payload.get('expires_in')
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            if expires_in else None
        )
        return access, refresh, expires_at

    # ------------------------------------------------------------------
    # Connection lifecycle (called by OAuth middleware)
    # ------------------------------------------------------------------
    async def save_service_connection(self, token_payload: Dict[str, Any], actor: User) -> ChallongeConnection:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only staff can connect the SGL Challonge account",
        )
        access, refresh, expires_at = self._unpack_token(token_payload)
        scopes = token_payload.get('scope') or _service_scopes()
        try:
            me = await self._oauth_client().get_me(access)
            username = me.get('username')
        except ChallongeAPIError:
            username = None
        connection = await self.repository.save_connection(
            access_token=access,
            refresh_token=refresh,
            token_expires_at=expires_at,
            scopes=scopes,
            challonge_username=username,
            connected_by=actor,
        )
        await self.audit_service.write_log(
            actor, AuditActions.CHALLONGE_CONNECTED, {'challonge_username': username},
        )
        return connection

    async def disconnect(self, actor: User) -> None:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only staff can disconnect the SGL Challonge account",
        )
        await self.repository.clear_connection()
        await self.audit_service.write_log(actor, AuditActions.CHALLONGE_DISCONNECTED, {})

    async def get_connection_status(self) -> Dict[str, Any]:
        connection = await self.repository.get_connection()
        usage = await self.repository.get_monthly_usage()
        base = {
            'configured': self.is_configured(),
            'request_usage': usage,
            'request_quota': CHALLONGE_MONTHLY_QUOTA,
        }
        if connection is None:
            return {'connected': False, **base}
        return {
            'connected': True,
            'challonge_username': connection.challonge_username,
            'scopes': connection.scopes,
            'token_expires_at': connection.token_expires_at,
            **base,
        }

    # ------------------------------------------------------------------
    # Player identity linking (called by player OAuth callback)
    # ------------------------------------------------------------------
    async def record_player_link(
        self, user: User, challonge_user_id: str, challonge_username: Optional[str], actor: User,
    ) -> None:
        user.challonge_user_id = challonge_user_id
        user.challonge_username = challonge_username
        user.challonge_linked_at = datetime.now(timezone.utc)
        await user.save()
        await self.audit_service.write_log(
            actor, AuditActions.CHALLONGE_PLAYER_LINKED,
            {'user_id': user.id, 'challonge_user_id': challonge_user_id, 'challonge_username': challonge_username},
        )

    async def participant_tournament_ids(self, user: User) -> Set[int]:
        """Tournament IDs whose mirrored Challonge bracket includes this user.

        Bracket membership is what drives tournament participation for linked
        tournaments, so the UI reads this instead of manual opt-in records.
        """
        return await self.repository.participant_tournament_ids_for_user(user)

    async def link_player_manually(
        self,
        user: User,
        challonge_user_id: str,
        challonge_username: Optional[str],
        actor: User,
    ) -> None:
        """Staff override to link a user to a Challonge account by id.

        Mirrors the OAuth ``record_player_link`` but is initiated by Staff (e.g.
        for a player who can't complete the OAuth flow). The id must be unique
        since participant matching resolves a single user per Challonge id.
        """
        cuid = (challonge_user_id or '').strip()
        if not cuid:
            raise ValueError('A Challonge account id is required to link this user.')
        existing = await User.filter(challonge_user_id=cuid).exclude(id=user.id).first()
        if existing is not None:
            raise ValueError(f'That Challonge account is already linked to {existing.username}.')
        user.challonge_user_id = cuid
        user.challonge_username = (challonge_username or '').strip() or None
        user.challonge_linked_at = datetime.now(timezone.utc)
        await user.save()
        await self.audit_service.write_log(
            actor, AuditActions.CHALLONGE_PLAYER_LINKED,
            {
                'user_id': user.id,
                'challonge_user_id': cuid,
                'challonge_username': user.challonge_username,
                'manual': True,
            },
        )

    async def set_player_username(
        self, user: User, challonge_username: Optional[str], actor: User,
    ) -> None:
        """Manually correct the linked Challonge username (Staff override).

        Participant matching keys off ``challonge_user_id``; this only fixes the
        display username, so it requires an already-linked account.
        """
        if not user.challonge_user_id:
            raise ValueError('This user has no linked Challonge account to edit.')
        new_username = (challonge_username or '').strip() or None
        if new_username == user.challonge_username:
            return
        old_username = user.challonge_username
        user.challonge_username = new_username
        await user.save()
        await self.audit_service.write_log(
            actor, AuditActions.CHALLONGE_PLAYER_USERNAME_UPDATED,
            {'user_id': user.id, 'old_username': old_username, 'new_username': new_username},
        )

    async def unlink_player(self, user: User, actor: User) -> None:
        user.challonge_user_id = None
        user.challonge_username = None
        user.challonge_linked_at = None
        await user.save()
        await self.audit_service.write_log(
            actor, AuditActions.CHALLONGE_PLAYER_UNLINKED, {'user_id': user.id},
        )

    async def exchange_player_code(self, code: str) -> Dict[str, Any]:
        """Exchange a player's authorization code and return their identity.

        Returns {'user_id', 'username'}. The token is used once and discarded.
        """
        payload = await self._oauth_client().exchange_code(code, _redirect_uri())
        access = payload.get('access_token')
        if not access:
            raise ChallongeAPIError(f"Challonge token response missing access_token: {payload}")
        return await self._oauth_client().get_me(access)

    async def exchange_service_code(self, code: str) -> Dict[str, Any]:
        """Exchange the service account's authorization code for a token payload."""
        return await self._oauth_client().exchange_code(code, _redirect_uri())

    # ------------------------------------------------------------------
    # Tournament linking + bracket sync
    # ------------------------------------------------------------------
    @staticmethod
    def parse_tournament_identifier(id_or_url: str) -> str:
        """Extract a Challonge tournament identifier from a raw id or URL.

        ``https://challonge.com/abc123``           -> ``abc123``
        ``https://user.challonge.com/abc123``       -> ``user-abc123``
        ``abc123`` / ``12345``                      -> unchanged
        """
        value = (id_or_url or '').strip()
        if not value:
            raise ValueError("Provide a Challonge tournament ID or URL.")
        if '://' not in value and '.challonge.com' not in value and '/' not in value:
            return value
        parsed = urlparse(value if '://' in value else f'https://{value}')
        slug = parsed.path.strip('/').split('/')[0]
        host = (parsed.hostname or '').lower()
        if host.endswith('.challonge.com'):
            subdomain = host[:-len('.challonge.com')]
            if subdomain and subdomain != 'www':
                return f"{subdomain}-{slug}"
        return slug or value

    async def link_tournament(self, tournament_id: int, id_or_url: str, actor: User) -> Tournament:
        tournament = await self.tournament_repository.get_by_id(tournament_id)
        if tournament is None:
            raise ValueError(f"Tournament {tournament_id} not found")
        await AuthService.ensure(
            await AuthService.can_edit_tournament(actor, tournament),
            "You do not have permission to link this tournament",
        )

        identifier = self.parse_tournament_identifier(id_or_url)
        try:
            full = await self._api_client().get_tournament_full(identifier)
        except ChallongeAPIError as e:
            raise ValueError(f"Could not find that Challonge tournament: {e}") from e

        remote = full['tournament']
        tournament.challonge_tournament_id = remote.get('id') or identifier
        tournament.challonge_tournament_url = remote.get('url')
        await tournament.save()

        await self.audit_service.write_log(
            actor, AuditActions.CHALLONGE_TOURNAMENT_LINKED,
            {'tournament_id': tournament.id, 'challonge_tournament_id': tournament.challonge_tournament_id},
        )

        # The full fetch already carries the bracket, so mirror it without a
        # second round-trip.
        await self._mirror_bracket(tournament, full['participants'], full['matches'], actor)
        return tournament

    async def sync_bracket(self, tournament_id: int, actor: User, force: bool = False) -> Dict[str, int]:
        tournament = await self.tournament_repository.get_by_id(tournament_id)
        if tournament is None:
            raise ValueError(f"Tournament {tournament_id} not found")
        await AuthService.ensure(
            await AuthService.can_edit_tournament(actor, tournament),
            "You do not have permission to sync this tournament",
        )
        return await self._sync_tournament(tournament, actor, force=force)

    async def _sync_tournament(
        self, tournament: Tournament, actor: User, force: bool = False,
    ) -> Dict[str, int]:
        """Fetch + mirror a linked bracket. Permission is the caller's concern.

        Shared by the admin sync action, the post-push auto re-sync, and the
        webhook receiver. A non-forced call within the throttle window of the
        last successful sync is a no-op (returns cached counts, no API request).
        """
        if not tournament.challonge_tournament_id:
            raise ValueError("This tournament is not linked to a Challonge tournament yet.")

        if not force and self._synced_recently(tournament):
            return {
                'participants': await self.repository.count_participants(tournament),
                'matches': await self.repository.count_matches(tournament),
                'skipped': True,
            }

        full = await self._api_client().get_tournament_full(tournament.challonge_tournament_id)
        result = await self._mirror_bracket(
            tournament, full['participants'], full['matches'], actor,
        )
        await self.repository.set_last_synced_at(tournament, datetime.now(timezone.utc))
        return result

    @staticmethod
    def _synced_recently(tournament: Tournament) -> bool:
        last = _as_aware_utc(tournament.challonge_last_synced_at)
        if last is None:
            return False
        return datetime.now(timezone.utc) - last < _SYNC_THROTTLE_WINDOW

    async def _mirror_bracket(
        self,
        tournament: Tournament,
        remote_participants: List[Dict[str, Any]],
        remote_matches: List[Dict[str, Any]],
        actor: User,
    ) -> Dict[str, int]:
        # Participants -> resolve to linked sglman users by Challonge account id.
        participant_by_cid: Dict[str, Any] = {}
        for rp in remote_participants:
            cuid = rp.get('challonge_user_id')
            user = await User.get_or_none(challonge_user_id=cuid) if cuid else None
            participant = await self.repository.upsert_participant(
                tournament=tournament,
                challonge_participant_id=rp['participant_id'],
                name=rp.get('name'),
                challonge_user_id=cuid,
                user=user,
            )
            participant_by_cid[rp['participant_id']] = participant

        # Matches -> mirror with resolved participant FKs.
        for rm in remote_matches:
            p1 = participant_by_cid.get(rm.get('player1_participant_id'))
            p2 = participant_by_cid.get(rm.get('player2_participant_id'))
            winner = participant_by_cid.get(rm.get('winner_participant_id'))
            await self.repository.upsert_match(
                tournament=tournament,
                challonge_match_id=rm['match_id'],
                round_=rm.get('round'),
                state=self._map_state(rm.get('state')),
                participant1=p1,
                participant2=p2,
                winner_participant=winner,
            )

        result = {'participants': len(remote_participants), 'matches': len(remote_matches)}
        await self.audit_service.write_log(
            actor, AuditActions.CHALLONGE_BRACKET_SYNCED, {'tournament_id': tournament.id, **result},
        )
        return result

    @staticmethod
    def _map_state(state: Optional[str]) -> ChallongeMatchState:
        if state == 'open':
            return ChallongeMatchState.OPEN
        if state == 'complete':
            return ChallongeMatchState.COMPLETE
        return ChallongeMatchState.PENDING

    # ------------------------------------------------------------------
    # Scheduling a bracket matchup (reuses the existing match-request flow)
    # ------------------------------------------------------------------
    async def list_unscheduled_matches_for_user(self, user: User) -> List[ChallongeMatch]:
        return await self.repository.unscheduled_open_matches_for_user(user)

    async def schedule_challonge_match(
        self,
        challonge_match_pk: int,
        scheduled_date: str,
        scheduled_time: str,
        actor: User,
        comment: Optional[str] = None,
    ) -> Match:
        cmatch = await self.repository.get_match(challonge_match_pk)
        if cmatch is None:
            raise ValueError("Challonge match not found")
        if cmatch.match_id is not None:
            raise ValueError("This match has already been scheduled.")
        if cmatch.state != ChallongeMatchState.OPEN:
            raise ValueError("This match isn't ready to schedule yet.")

        p1, p2 = cmatch.participant1, cmatch.participant2
        if p1 is None or p2 is None or p1.user is None or p2.user is None:
            raise ValueError(
                "Both players must link their Challonge account before this match can be scheduled."
            )

        match = await MatchService().submit_match_request(
            tournament_id=cmatch.tournament_id,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            player_ids=[p1.user_id, p2.user_id],
            actor=actor,
            comment=comment,
        )
        await self.repository.link_match(cmatch, match)
        return match

    # ------------------------------------------------------------------
    # Pushing results back to Challonge
    # ------------------------------------------------------------------
    async def push_result_if_linked(self, match: Match, actor: Optional[User]) -> bool:
        """Push the result only when the match mirrors a Challonge match.

        Returns True if a push was attempted. Used by the confirm flow so
        non-Challonge matches are silently skipped. Requires an actor for the
        audit entry; with none, the push is skipped.
        """
        if actor is None:
            return False
        cmatch = await self.repository.get_challonge_match_for_match(match)
        if cmatch is None:
            return False
        await self.push_match_result(match, actor)
        return True

    async def push_match_result(self, match: Match, actor: User) -> None:
        cmatch = await self.repository.get_challonge_match_for_match(match)
        if cmatch is None:
            raise ValueError("This match is not linked to a Challonge match.")

        await match.fetch_related('players__user', 'tournament')
        ranked = [p for p in match.players if p.finish_rank is not None]
        winner = next((p for p in ranked if p.finish_rank == 1), None)
        if winner is None:
            raise ValueError("No winner has been recorded for this match yet.")
        losers = [p for p in match.players if p.id != winner.id]
        if not losers:
            raise ValueError("Cannot push a result without an opponent.")
        loser = losers[0]

        winner_pid = self._participant_id_for_user(cmatch, winner.user_id)
        loser_pid = self._participant_id_for_user(cmatch, loser.user_id)
        if winner_pid is None or loser_pid is None:
            raise ValueError("Could not map both players to Challonge participants; re-sync the bracket.")

        if not cmatch.tournament.challonge_tournament_id:
            raise ValueError("The tournament is no longer linked to Challonge.")

        await self._api_client().update_match(
            tournament_id=cmatch.tournament.challonge_tournament_id,
            match_id=cmatch.challonge_match_id,
            winner_participant_id=winner_pid,
            loser_participant_id=loser_pid,
        )
        await self.audit_service.write_log(
            actor, AuditActions.CHALLONGE_RESULT_PUSHED,
            {'match_id': match.id, 'challonge_match_id': cmatch.challonge_match_id,
             'winner_participant_id': winner_pid},
        )

        # The push advanced the bracket (next-round matches now open). Re-sync
        # once so those newly-open matches surface locally without a manual
        # Sync. Failures here must not undo the successful push.
        try:
            await self._sync_tournament(cmatch.tournament, actor, force=True)
        except (ValueError, ChallongeAPIError) as e:
            print(f"[challonge] post-push re-sync failed for tournament "
                  f"{cmatch.tournament_id}: {e}")

    @staticmethod
    def _participant_id_for_user(cmatch: ChallongeMatch, user_id: int) -> Optional[str]:
        for participant in (cmatch.participant1, cmatch.participant2):
            if participant is not None and participant.user_id == user_id:
                return participant.challonge_participant_id
        return None
