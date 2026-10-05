"""
Check-in Service - Business Logic Layer

Runs the check-in desk for in-person events. Registration happens on
Matcherino; this service mirrors a bounty's participant list into
:class:`~models.CheckInEntrant` rows, matches each registrant to a Wizzrobe
account where it can, and records who has checked in. Walk-ups are added by
staff at the desk.

Matching to an account is a nice-to-have, never a precondition: an entrant with
no ``user`` checks in like anyone else.

The Matcherino endpoints are unofficial (see ``matcherino_client``), so a sync
that fails, or that comes back empty while the roster has rows, records the
error and changes nothing. Withdrawing everyone because one response was bad is
the failure this guards against.
"""

import asyncio
import difflib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from tortoise.exceptions import IntegrityError

from application.errors import require_found
from application.events import Event, EventType, check_in_live, event_bus
from application.feature_flags import requires_feature
from application.repositories import (
    CheckInEntrantRepository,
    CheckInEventRepository,
    CheckInUserLookupRepository,
    UserRepository,
)
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.check_in_rules import (
    CheckInOutcome,
    IdentityLookups,
    SyncResult,
    handle_id,
    norm_name,
    resolve_link,
    summarize,
)
from application.utils.clients.matcherino_client import (
    MatcherinoAPIError,
    MatcherinoBounty,
    MatcherinoClient,
    MatcherinoParticipant,
    get_matcherino_client,
)
from models import (
    CheckInEntrant,
    CheckInEntrantSource,
    CheckInEvent,
    CheckInEventStatus,
    CheckInLinkMethod,
    FeatureFlag,
    User,
)

MIN_SYNC_INTERVAL_MINUTES = 1
MAX_SYNC_INTERVAL_MINUTES = 120
SUGGESTION_LIMIT = 3
SUGGESTION_THRESHOLD = 0.6

_DESK_DENIED = 'Only staff and check-in desk volunteers can do that.'
_STAFF_DENIED = 'Only staff can do that.'


# One sync per event at a time. The app runs as a single process
# (docs/scaling-roadmap.md), so an in-process lock serialises the worker's poll,
# a staff Sync and every desk phone's Sync for the same event.
_sync_locks: Dict[int, asyncio.Lock] = {}


def _sync_lock(event_id: int) -> asyncio.Lock:
    return _sync_locks.setdefault(event_id, asyncio.Lock())


class CheckInService:
    """Check-in events, the Matcherino sync, and the desk's actions."""

    def __init__(self, client: Optional[MatcherinoClient] = None) -> None:
        self.events = CheckInEventRepository()
        self.entrants = CheckInEntrantRepository()
        self.lookup = CheckInUserLookupRepository()
        self.audit_service = AuditService()
        self._client = client

    @property
    def client(self) -> MatcherinoClient:
        if self._client is None:
            self._client = get_matcherino_client()
        return self._client

    # --- Events (staff) ---

    @staticmethod
    def _clean_event_fields(
        name: str, bounty_id: Optional[int], sync_interval_minutes: int,
    ) -> Tuple[str, Optional[int], int]:
        name = (name or '').strip()
        if not name:
            raise ValueError('Give the event a name.')
        if bounty_id is not None and bounty_id <= 0:
            raise ValueError('A Matcherino bounty ID is a positive number.')
        if not MIN_SYNC_INTERVAL_MINUTES <= sync_interval_minutes <= MAX_SYNC_INTERVAL_MINUTES:
            raise ValueError(
                f'Sync every {MIN_SYNC_INTERVAL_MINUTES} to {MAX_SYNC_INTERVAL_MINUTES} minutes.'
            )
        return name, bounty_id, sync_interval_minutes

    async def _ensure_bounty_free(self, bounty_id: Optional[int], event_id: Optional[int] = None) -> None:
        if bounty_id is None:
            return
        existing = await self.events.get_by_bounty(bounty_id)
        if existing is not None and existing.id != event_id:
            raise ValueError(f'Bounty {bounty_id} is already used by "{existing.name}".')

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def create_event(
        self,
        actor: User,
        name: str,
        bounty_id: Optional[int] = None,
        status: CheckInEventStatus = CheckInEventStatus.DRAFT,
        sync_interval_minutes: int = 5,
    ) -> CheckInEvent:
        await AuthService.ensure(await AuthService.can_manage_check_in(actor), _STAFF_DENIED)
        name, bounty_id, sync_interval_minutes = self._clean_event_fields(
            name, bounty_id, sync_interval_minutes,
        )
        await self._ensure_bounty_free(bounty_id)
        try:
            event = await self.events.create(
                name=name, matcherino_bounty_id=bounty_id, status=status,
                sync_interval_minutes=sync_interval_minutes,
            )
        except IntegrityError as e:
            raise ValueError(f'Bounty {bounty_id} is already used by another event.') from e
        await self.audit_service.write_log(
            actor, AuditActions.CHECK_IN_EVENT_CREATED,
            {'event_id': event.id, 'name': name, 'bounty_id': bounty_id, 'status': status.value},
        )
        return event

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def update_event(
        self,
        actor: User,
        event_id: int,
        name: str,
        bounty_id: Optional[int],
        status: CheckInEventStatus,
        sync_interval_minutes: int,
    ) -> CheckInEvent:
        await AuthService.ensure(await AuthService.can_manage_check_in(actor), _STAFF_DENIED)
        event = require_found(await self.events.get_by_id(event_id), 'Check-in event')
        name, bounty_id, sync_interval_minutes = self._clean_event_fields(
            name, bounty_id, sync_interval_minutes,
        )
        await self._ensure_bounty_free(bounty_id, event.id)
        if bounty_id != event.matcherino_bounty_id and await self.entrants.has_matcherino_rows(event):
            raise ValueError(
                "This event already has a Matcherino roster, so its bounty can't change: "
                'the next sync would mark everyone on it as withdrawn. Create a new event instead.'
            )
        changed = {
            key: value
            for key, value in (
                ('name', name), ('matcherino_bounty_id', bounty_id), ('status', status),
                ('sync_interval_minutes', sync_interval_minutes),
            )
            if getattr(event, key) != value
        }
        if not changed:
            return event
        await self.events.update(event, **changed)
        await self.audit_service.write_log(
            actor, AuditActions.CHECK_IN_EVENT_UPDATED,
            {'event_id': event.id, 'changed': {
                key: (value.value if isinstance(value, CheckInEventStatus) else value)
                for key, value in changed.items()
            }},
        )
        check_in_live.publish(event.id, None, check_in_live.ROSTER)
        return event

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def delete_event(self, actor: User, event_id: int) -> None:
        await AuthService.ensure(await AuthService.can_manage_check_in(actor), _STAFF_DENIED)
        event = require_found(await self.events.get_by_id(event_id), 'Check-in event')
        entrants = await self.entrants.list_for_event(event)
        counts = summarize(entrants)
        await self.events.delete(event)
        await self.audit_service.write_log(
            actor, AuditActions.CHECK_IN_EVENT_DELETED,
            {'event_id': event_id, 'name': event.name,
             'entrants': len(entrants), 'checked_in': counts.checked_in},
        )
        check_in_live.publish(event_id, None, check_in_live.DELETED)

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def preview_bounty(self, actor: User, bounty_id: int) -> MatcherinoBounty:
        """Look a bounty up on Matcherino so staff can confirm it before saving."""
        await AuthService.ensure(await AuthService.can_manage_check_in(actor), _STAFF_DENIED)
        try:
            return await self.client.fetch_bounty(bounty_id)
        except MatcherinoAPIError as e:
            raise ValueError(f"Couldn't find that bounty on Matcherino: {e}") from e

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def list_events(self) -> List[CheckInEvent]:
        return await self.events.list_all()

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def list_open_events(self) -> List[CheckInEvent]:
        return await self.events.list_by_status(CheckInEventStatus.OPEN)

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def get_event(self, event_id: int) -> Optional[CheckInEvent]:
        return await self.events.get_by_id(event_id)

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def has_open_event(self) -> bool:
        return await self.events.exists_with_status(CheckInEventStatus.OPEN)

    # --- Matcherino sync ---

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def sync_event(self, actor: User, event_id: int, *, audit: bool = True) -> SyncResult:
        """Mirror the bounty's participants into the roster and auto-link them.

        ``audit=False`` is the worker's poll: it still publishes the domain
        event, but writes no audit row every few minutes.
        """
        await AuthService.ensure(await AuthService.can_run_check_in_desk(actor), _DESK_DENIED)
        async with _sync_lock(event_id):
            event = require_found(await self.events.get_by_id(event_id), 'Check-in event')
            if event.matcherino_bounty_id is None:
                raise ValueError("This event isn't linked to a Matcherino bounty.")
            try:
                fetched = await self.client.fetch_participants(event.matcherino_bounty_id)
                # Read after the fetch, so desk actions made while it ran are seen.
                existing = await self.entrants.matcherino_rows_by_user_id(event)
                if not fetched and any(row.withdrawn_at is None for row in existing.values()):
                    raise MatcherinoAPIError(
                        'Matcherino returned no registrants for a bounty that had some'
                    )
            except MatcherinoAPIError as e:
                # updated_at marks when it failed: the desk shows it and the
                # worker backs off from it.
                await self.events.record_sync(
                    event, last_sync_error=str(e)[:1000], updated_at=datetime.now(timezone.utc),
                )
                check_in_live.publish(event.id, None, check_in_live.ROSTER)
                raise ValueError(
                    f"Couldn't sync with Matcherino, so the roster wasn't changed. {e}"
                ) from e
            try:
                result = await self._apply_roster(actor, event, fetched, existing)
            except IntegrityError as e:
                raise ValueError(
                    'The roster changed while syncing. Try Sync again in a moment.'
                ) from e

        details = {'event_id': event.id, 'bounty_id': event.matcherino_bounty_id, **result.as_dict()}
        if audit:
            await self.audit_service.write_and_publish(
                actor, AuditActions.CHECK_IN_EVENT_SYNCED, details, EventType.CHECK_IN_EVENT_SYNCED,
            )
        else:
            event_bus.publish(Event.create(EventType.CHECK_IN_EVENT_SYNCED, details, actor))
        check_in_live.publish(event.id, None, check_in_live.ROSTER)
        return result

    async def _apply_roster(
        self,
        actor: User,
        event: CheckInEvent,
        fetched: Sequence[MatcherinoParticipant],
        existing: Dict[str, CheckInEntrant],
    ) -> SyncResult:
        now = datetime.now(timezone.utc)
        participants: Dict[str, MatcherinoParticipant] = {}
        for participant in fetched:
            participants.setdefault(participant.user_id, participant)

        result = SyncResult(total=len(participants))
        created: List[CheckInEntrant] = []
        touched: Dict[int, Tuple[CheckInEntrant, set]] = {}

        for user_id, participant in participants.items():
            fields = self._participant_fields(participant)
            row = existing.get(user_id)
            if row is None:
                created.append(CheckInEntrant(
                    event=event, source=CheckInEntrantSource.MATCHERINO, matcherino_user_id=user_id,
                    **fields,
                ))
                continue
            changes = {key for key, value in fields.items() if getattr(row, key) != value}
            for key in changes:
                setattr(row, key, fields[key])
            if row.withdrawn_at is not None:
                row.withdrawn_at = None  # type: ignore[assignment]
                changes.add('withdrawn_at')
                result.rejoined += 1
            if changes:
                touched[row.id] = (row, changes)
                result.updated += 1

        for user_id, row in existing.items():
            if user_id not in participants and row.withdrawn_at is None:
                row.withdrawn_at = now
                touched[row.id] = (row, touched.get(row.id, (row, set()))[1] | {'withdrawn_at'})
                result.withdrawn += 1

        unlinked = [
            row for row in [*created, *existing.values()]
            if row.user_id is None and row.link_method != CheckInLinkMethod.MANUAL
        ]
        matches = await self._auto_link_matches(event, unlinked) if unlinked else []
        new_rows = {id(row) for row in created}
        linked: List[Tuple[CheckInEntrant, User, CheckInLinkMethod]] = []
        for row, user, method in matches:
            if id(row) in new_rows:
                row.user = user
                row.link_method = method
                linked.append((row, user, method))

        result.added = len(created)
        if created:
            await self.entrants.bulk_create(created)
        for row, changes in touched.values():
            await self.entrants.save(row, [*changes, 'updated_at'])
        for row, user, method in matches:
            if id(row) in new_rows:
                continue
            # Conditional: a desk may have linked or unlinked this row meanwhile.
            if await self.entrants.claim_auto_link(row, user, method, now):
                row.user = user
                row.link_method = method
                linked.append((row, user, method))
        for row, user, method in linked:
            await self._remember_matcherino_account(actor, user, row, method)
        result.auto_linked = len(linked)

        await self.events.record_sync(
            event, last_synced_at=now, last_sync_error=None, last_sync_count=result.total,
        )
        return result

    @staticmethod
    def _participant_fields(participant: MatcherinoParticipant) -> Dict[str, object]:
        return {
            'display_name': participant.display_name[:255],
            'avatar_url': (participant.avatar_url or '')[:512] or None,
            'auth_provider': participant.auth_provider,
            'auth_id': participant.auth_id,
            'twitch_login': participant.twitch_login,
            'registered_at': participant.registered_at,
            'source_data': participant.raw,
        }

    async def _auto_link_matches(
        self, event: CheckInEvent, rows: Sequence[CheckInEntrant],
    ) -> List[Tuple[CheckInEntrant, User, CheckInLinkMethod]]:
        """The account each row's identifiers name exactly, one row per account.

        Exact identifiers only, matched across all of Wizzrobe: a registrant's
        Discord or Twitch id is already public on the bounty, so finding the
        account it belongs to reveals nothing new. Fuzzy name matches are only
        ever *suggested* (:meth:`suggest_users`), never applied.
        """
        lookups = await self._build_lookups(rows)
        taken = await self.entrants.linked_user_ids(event)
        matches: List[Tuple[CheckInEntrant, User, CheckInLinkMethod]] = []
        for row in rows:
            match = resolve_link(row, lookups)
            if match is None or match[0].id in taken:
                continue
            taken.add(match[0].id)
            matches.append((row, *match))
        return matches

    async def _build_lookups(self, rows: Sequence[CheckInEntrant]) -> IdentityLookups:
        discord_ids = {
            int(row.auth_id) for row in rows
            if row.auth_provider == 'discord' and (row.auth_id or '').isdigit()
        }
        twitch_ids = {row.auth_id for row in rows if row.auth_provider == 'twitch' and row.auth_id}
        twitch_logins = {row.twitch_login for row in rows if row.twitch_login}
        matcherino_ids = {row.matcherino_user_id for row in rows if row.matcherino_user_id}
        users = await self.lookup.users_by_identifiers(
            discord_ids=discord_ids, twitch_ids=twitch_ids,
            twitch_logins=twitch_logins, matcherino_ids=matcherino_ids,
        )
        lookups = IdentityLookups()
        for user in users:
            if user.matcherino_user_id:
                lookups.by_matcherino_id[user.matcherino_user_id] = user
            if user.discord_id is not None:
                lookups.by_discord_id[str(user.discord_id)] = user
            if user.twitch_user_id:
                lookups.by_twitch_id[user.twitch_user_id] = user
            if user.twitch_username:
                lookups.by_twitch_login[user.twitch_username.lower()] = user
        if matcherino_ids - set(lookups.by_matcherino_id):
            for user in await self.lookup.users_with_unverified_handle():
                hid = handle_id(user.matcherino_username)
                if hid in matcherino_ids:
                    lookups.by_handle_id.setdefault(hid, user)
        return lookups

    async def _remember_matcherino_account(
        self, actor: User, user: User, entrant: CheckInEntrant, method: CheckInLinkMethod,
    ) -> None:
        """Record the Matcherino account on the user, filling only what is empty.

        Only from evidence that the account is theirs: an OAuth-verified Discord
        or Twitch id, or a person at the desk confirming it. A match on the
        handle the user typed is *not* promoted — that handle is self-asserted,
        and it keeps matching on its own anyway. Never overwrites a handle the
        player typed, never takes an id another account holds, and is audited,
        because ``matcherino_username`` is where prize money is sent.
        """
        if not entrant.matcherino_user_id or method in (
            CheckInLinkMethod.MATCHERINO_HANDLE, CheckInLinkMethod.MATCHERINO_ID,
        ):
            return
        fields: Dict[str, object] = {}
        if not user.matcherino_user_id:
            holder = await self.lookup.user_with_matcherino_id(entrant.matcherino_user_id)
            if holder is None:
                fields['matcherino_user_id'] = entrant.matcherino_user_id
        if not user.matcherino_username:
            fields['matcherino_username'] = f'{entrant.display_name}#{entrant.matcherino_user_id}'
        if not fields:
            return
        await UserRepository.update(user, **fields)
        await self.audit_service.write_log(
            actor, AuditActions.USER_PROFILE_UPDATED,
            {'user_id': user.id, 'source': 'check_in', 'entrant_id': entrant.id,
             'link_method': method.value, 'changed': fields},
        )

    async def _forget_matcherino_account(self, actor: User, user: User, entrant: CheckInEntrant) -> None:
        """Undo what :meth:`_remember_matcherino_account` recorded for this account.

        Staff unlink when a match was wrong, which means this Matcherino account
        isn't this person's: left in place, the id would re-link them at every
        later event and lock the real owner out. The handle is cleared only if
        it is still exactly the one check-in filled in.
        """
        if not entrant.matcherino_user_id:
            return
        fields: Dict[str, object] = {}
        if user.matcherino_user_id == entrant.matcherino_user_id:
            fields['matcherino_user_id'] = None
        if user.matcherino_username == f'{entrant.display_name}#{entrant.matcherino_user_id}':
            fields['matcherino_username'] = None
        if not fields:
            return
        await UserRepository.update(user, **fields)
        await self.audit_service.write_log(
            actor, AuditActions.USER_PROFILE_UPDATED,
            {'user_id': user.id, 'source': 'check_in', 'entrant_id': entrant.id,
             'changed': fields},
        )

    # --- Roster reads ---

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def roster(self, event: CheckInEvent) -> List[CheckInEntrant]:
        return await self.entrants.list_for_event(event)

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def get_entrant(self, entrant_id: int) -> Optional[CheckInEntrant]:
        return await self.entrants.get_by_id(entrant_id)

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def suggest_users(self, entrant: CheckInEntrant, limit: int = SUGGESTION_LIMIT) -> List[User]:
        """Community members whose names look like the registrant's.

        A suggestion for staff to confirm, never applied on its own. Members
        already linked to someone else on this roster are left out.
        """
        target = norm_name(entrant.display_name)
        targets = {target, norm_name(entrant.twitch_login)} - {''}
        if not targets:
            return []
        taken = await self.entrants.linked_user_ids(entrant.event)
        scored: List[Tuple[float, User]] = []
        for user in await UserRepository.get_community_people():
            if user.id in taken:
                continue
            names = {
                norm_name(user.username), norm_name(user.display_name), norm_name(user.twitch_username),
                norm_name((user.matcherino_username or '').split('#')[0]),
            } - {''}
            score = max(
                (difflib.SequenceMatcher(None, t, n).ratio() for t in targets for n in names),
                default=0.0,
            )
            if score >= SUGGESTION_THRESHOLD:
                scored.append((score, user))
        scored.sort(key=lambda pair: (-pair[0], pair[1].username.lower()))
        return [user for _, user in scored[:limit]]

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def search_members(self, event: CheckInEvent, query: str, limit: int = 20) -> List[User]:
        """Community members not yet on this roster, matching ``query``.

        Backs the member search in the link and walk-up dialogs.
        """
        needle = norm_name(query)
        if len(needle) < 2:
            return []
        taken = await self.entrants.linked_user_ids(event)
        matches = [
            user for user in await UserRepository.get_community_people()
            if user.id not in taken and any(
                needle in norm_name(name)
                for name in (user.username, user.display_name, user.twitch_username,
                             user.matcherino_username)
            )
        ]
        return matches[:limit]

    # --- Desk actions ---

    async def _entrant_for_desk(self, actor: User, entrant_id: int) -> CheckInEntrant:
        await AuthService.ensure(await AuthService.can_run_check_in_desk(actor), _DESK_DENIED)
        return require_found(await self.entrants.get_by_id(entrant_id), 'Roster entry')

    @staticmethod
    def _entrant_details(entrant: CheckInEntrant) -> Dict[str, object]:
        return {
            'event_id': entrant.event_id, 'entrant_id': entrant.id,
            'user_id': entrant.user_id, 'display_name': entrant.display_name,
            'matcherino_user_id': entrant.matcherino_user_id,
        }

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def check_in(self, actor: User, entrant_id: int) -> CheckInOutcome:
        """Check someone in. Doing it twice is not an error: it reports who did it first.

        The write is conditional, so two phones tapping the same person at once
        record one check-in, one audit row and one event.
        """
        entrant = await self._entrant_for_desk(actor, entrant_id)
        now = datetime.now(timezone.utc)
        if entrant.checked_in_at is not None or not await self.entrants.claim_check_in(entrant, now, actor):
            return CheckInOutcome(await self.entrants.get_by_id(entrant_id) or entrant, already=True)
        entrant.checked_in_at = now
        entrant.checked_in_by = actor
        await self.audit_service.write_and_publish(
            actor, AuditActions.CHECK_IN_ENTRANT_CHECKED_IN, self._entrant_details(entrant),
            EventType.CHECK_IN_ENTRANT_CHECKED_IN,
        )
        check_in_live.publish(entrant.event_id, entrant.id, check_in_live.CHANGED)
        return CheckInOutcome(entrant)

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def undo_check_in(self, actor: User, entrant_id: int) -> CheckInEntrant:
        entrant = await self._entrant_for_desk(actor, entrant_id)
        if entrant.checked_in_at is None or not await self.entrants.release_check_in(
            entrant, datetime.now(timezone.utc),
        ):
            return entrant
        entrant.checked_in_at = None  # type: ignore[assignment]
        entrant.checked_in_by = None
        await self.audit_service.write_and_publish(
            actor, AuditActions.CHECK_IN_ENTRANT_CHECK_IN_UNDONE, self._entrant_details(entrant),
            EventType.CHECK_IN_ENTRANT_CHECK_IN_UNDONE,
        )
        check_in_live.publish(entrant.event_id, entrant.id, check_in_live.CHANGED)
        return entrant

    @staticmethod
    async def _linkable_user(user_id: int) -> User:
        user = require_found(await UserRepository.get_by_id(user_id), 'User')
        if user.is_system or not user.is_active:
            raise ValueError("That account can't be linked.")
        return user

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def link(self, actor: User, entrant_id: int, user_id: int) -> CheckInEntrant:
        entrant = await self._entrant_for_desk(actor, entrant_id)
        user = await self._linkable_user(user_id)
        if entrant.user_id == user.id:
            return entrant
        other = await self.entrants.get_for_user(entrant.event, user)
        if other is not None:
            raise ValueError(f'{user.preferred_name} is already on this roster as {other.display_name}.')
        if entrant.matcherino_user_id:
            holder = await self.lookup.user_with_matcherino_id(entrant.matcherino_user_id)
            if holder is not None and holder.id != user.id:
                raise ValueError(
                    f'That Matcherino account is already linked to {holder.preferred_name}.'
                )
        entrant.user = user
        entrant.link_method = CheckInLinkMethod.MANUAL
        entrant.linked_by = actor
        try:
            await self.entrants.save(entrant, ['user_id', 'link_method', 'linked_by_id', 'updated_at'])
        except IntegrityError as e:
            raise ValueError(f'{user.preferred_name} was just added to this roster by someone else.') from e
        await self._remember_matcherino_account(actor, user, entrant, CheckInLinkMethod.MANUAL)
        await self.audit_service.write_and_publish(
            actor, AuditActions.CHECK_IN_ENTRANT_LINKED, self._entrant_details(entrant),
            EventType.CHECK_IN_ENTRANT_LINKED,
        )
        check_in_live.publish(entrant.event_id, entrant.id, check_in_live.CHANGED)
        return entrant

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def unlink(self, actor: User, entrant_id: int) -> CheckInEntrant:
        """Detach the account from this roster row.

        The row is marked ``MANUAL`` with no user, which tells the sync not to
        auto-link it again: staff unlink precisely when a match was wrong. For
        the same reason the Matcherino id the link recorded on the account is
        cleared (:meth:`_forget_matcherino_account`).
        """
        entrant = await self._entrant_for_desk(actor, entrant_id)
        if entrant.user_id is None:
            return entrant
        previous_user = entrant.user
        previous_user_id = entrant.user_id
        entrant.user = None
        entrant.link_method = CheckInLinkMethod.MANUAL
        entrant.linked_by = actor
        await self.entrants.save(entrant, ['user_id', 'link_method', 'linked_by_id', 'updated_at'])
        if previous_user is not None:
            await self._forget_matcherino_account(actor, previous_user, entrant)
        await self.audit_service.write_and_publish(
            actor, AuditActions.CHECK_IN_ENTRANT_UNLINKED,
            {**self._entrant_details(entrant), 'user_id': previous_user_id},
            EventType.CHECK_IN_ENTRANT_UNLINKED,
        )
        check_in_live.publish(entrant.event_id, entrant.id, check_in_live.CHANGED)
        return entrant

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def add_walk_up(
        self,
        actor: User,
        event_id: int,
        *,
        user_id: Optional[int] = None,
        name: Optional[str] = None,
        check_in: bool = True,
    ) -> CheckInEntrant:
        """Add someone who isn't registered on Matcherino. Staff only."""
        await AuthService.ensure(await AuthService.can_manage_check_in(actor), _STAFF_DENIED)
        event = require_found(await self.events.get_by_id(event_id), 'Check-in event')
        user = await self._linkable_user(user_id) if user_id else None
        if user is not None:
            other = await self.entrants.get_for_user(event, user)
            if other is not None:
                raise ValueError(f'{user.preferred_name} is already on this roster as {other.display_name}.')
            display_name = user.preferred_name
        else:
            display_name = (name or '').strip()
            if not display_name:
                raise ValueError('Pick a member or type their name.')
        now = datetime.now(timezone.utc)
        try:
            entrant = await self.entrants.create(
                event=event,
                source=CheckInEntrantSource.WALK_UP,
                display_name=display_name[:255],
                user=user,
                link_method=CheckInLinkMethod.WALK_UP if user else None,
                linked_by=actor if user else None,
                checked_in_at=now if check_in else None,
                checked_in_by=actor if check_in else None,
            )
        except IntegrityError as e:
            raise ValueError('That member was just added to this roster by someone else.') from e
        await self.audit_service.write_and_publish(
            actor, AuditActions.CHECK_IN_ENTRANT_WALK_UP_ADDED,
            {**self._entrant_details(entrant), 'checked_in': check_in},
            EventType.CHECK_IN_ENTRANT_WALK_UP_ADDED,
        )
        check_in_live.publish(event.id, entrant.id, check_in_live.CREATED)
        return entrant

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def remove_entrant(self, actor: User, entrant_id: int) -> None:
        """Delete a walk-up added by mistake. Staff only.

        Matcherino rows can't be removed here: the next sync would bring them
        straight back. Someone who isn't coming leaves the bounty, and the sync
        marks them withdrawn.
        """
        await AuthService.ensure(await AuthService.can_manage_check_in(actor), _STAFF_DENIED)
        entrant = require_found(await self.entrants.get_by_id(entrant_id), 'Roster entry')
        if entrant.source != CheckInEntrantSource.WALK_UP:
            raise ValueError(
                "Matcherino registrations come back on the next sync, so they can't be "
                'removed here. Ask them to leave the bounty instead.'
            )
        details = self._entrant_details(entrant)
        event_id = entrant.event_id
        await self.entrants.delete(entrant)
        await self.audit_service.write_and_publish(
            actor, AuditActions.CHECK_IN_ENTRANT_REMOVED, details, EventType.CHECK_IN_ENTRANT_REMOVED,
        )
        check_in_live.publish(event_id, entrant_id, check_in_live.DELETED)
