"""
Check-in Repository - Data Access Layer

Check-in events and the entrants on their rosters.
"""

from typing import Dict, Iterable, List, Optional

from tortoise.expressions import Q
from tortoise.functions import Lower

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import CheckInEntrant, CheckInEvent, CheckInEventStatus, CheckInLinkMethod, User


class CheckInEventRepository(TenantScopedRepository[CheckInEvent]):
    model = CheckInEvent

    @staticmethod
    async def list_all() -> List[CheckInEvent]:
        return await scoped(CheckInEvent.all()).order_by('-created_at')

    @staticmethod
    async def list_by_status(status: CheckInEventStatus) -> List[CheckInEvent]:
        return await scoped(CheckInEvent.filter(status=status)).order_by('-created_at')

    @staticmethod
    async def exists_with_status(status: CheckInEventStatus) -> bool:
        return await scoped(CheckInEvent.filter(status=status)).exists()

    @staticmethod
    async def record_sync(event: CheckInEvent, **fields: object) -> None:
        """Write only the sync bookkeeping columns.

        A sync holds its ``event`` across a slow network fetch; a full save
        would revert anything staff changed on the event meanwhile.
        """
        await scoped(CheckInEvent.filter(id=event.id)).update(**fields)
        for key, value in fields.items():
            setattr(event, key, value)

    @staticmethod
    async def get_by_bounty(bounty_id: int) -> Optional[CheckInEvent]:
        return await scoped(CheckInEvent.filter(matcherino_bounty_id=bounty_id)).first()

    @staticmethod
    async def list_syncable_all() -> List[CheckInEvent]:
        """Open events with a Matcherino bounty, across every tenant.

        Deliberately cross-tenant: this is the sync worker's scan, which then
        runs each event inside its own ``tenant_scope``.
        """
        return await CheckInEvent.filter(
            status=CheckInEventStatus.OPEN, matcherino_bounty_id__isnull=False,
        )


class CheckInEntrantRepository(TenantScopedRepository[CheckInEntrant]):
    model = CheckInEntrant

    @staticmethod
    async def get_by_id(obj_id: int) -> Optional[CheckInEntrant]:
        return await CheckInEntrant.get_or_none(
            id=obj_id, tenant_id=current_tenant_id(),
        ).prefetch_related('user', 'event', 'checked_in_by')

    @staticmethod
    async def list_for_event(event: CheckInEvent) -> List[CheckInEntrant]:
        return await scoped(CheckInEntrant.filter(event=event)).order_by(
            'display_name',
        ).prefetch_related('user', 'checked_in_by')

    @staticmethod
    async def matcherino_rows_by_user_id(event: CheckInEvent) -> Dict[str, CheckInEntrant]:
        rows = await scoped(CheckInEntrant.filter(event=event, matcherino_user_id__isnull=False))
        return {row.matcherino_user_id: row for row in rows}

    @staticmethod
    async def linked_user_ids(event: CheckInEvent) -> set[int]:
        rows = await scoped(CheckInEntrant.filter(event=event, user_id__isnull=False)).values_list(
            'user_id', flat=True,
        )
        return set(rows)

    @staticmethod
    async def get_for_user(event: CheckInEvent, user: User) -> Optional[CheckInEntrant]:
        return await scoped(CheckInEntrant.filter(event=event, user=user)).first()

    @staticmethod
    async def has_matcherino_rows(event: CheckInEvent) -> bool:
        return await scoped(CheckInEntrant.filter(event=event, matcherino_user_id__isnull=False)).exists()

    @staticmethod
    async def claim_check_in(entrant: CheckInEntrant, at, by: User) -> bool:
        """Set the check-in only if nobody has yet; False when someone beat us to it."""
        updated = await scoped(CheckInEntrant.filter(id=entrant.id, checked_in_at__isnull=True)).update(
            checked_in_at=at, checked_in_by_id=by.id, updated_at=at,
        )
        return bool(updated)

    @staticmethod
    async def release_check_in(entrant: CheckInEntrant, at) -> bool:
        updated = await scoped(CheckInEntrant.filter(id=entrant.id, checked_in_at__isnull=False)).update(
            checked_in_at=None, checked_in_by_id=None, updated_at=at,
        )
        return bool(updated)

    @staticmethod
    async def claim_auto_link(entrant: CheckInEntrant, user: User, method, at) -> bool:
        """Link a row only if it is still unlinked and staff haven't unlinked it on purpose."""
        updated = await scoped(
            CheckInEntrant.filter(id=entrant.id, user_id__isnull=True)
            .filter(Q(link_method__isnull=True) | Q(link_method__not=CheckInLinkMethod.MANUAL.value))
        ).update(user_id=user.id, link_method=method, updated_at=at)
        return bool(updated)

    @staticmethod
    async def bulk_create(entrants: List[CheckInEntrant]) -> None:
        tenant_id = current_tenant_id()
        for entrant in entrants:
            entrant.tenant_id = tenant_id
        await CheckInEntrant.bulk_create(entrants)

    @staticmethod
    async def save(entrant: CheckInEntrant, fields: Iterable[str]) -> None:
        await entrant.save(update_fields=list(fields))


class CheckInUserLookupRepository:
    """Global identity lookups for matching registrants to accounts.

    ``User`` has no tenant column; these are deliberately unscoped (global)
    exact-identifier lookups. Who may be *offered* as a manual match is a
    separate, community-scoped question answered by ``UserRepository``.
    """

    @staticmethod
    async def users_by_identifiers(
        *,
        discord_ids: Iterable[int],
        twitch_ids: Iterable[str],
        twitch_logins: Iterable[str],
        matcherino_ids: Iterable[str],
    ) -> List[User]:
        clauses = [
            Q(**{f'{column}__in': values})
            for column, values in (
                ('discord_id', list(discord_ids)),
                ('twitch_user_id', list(twitch_ids)),
                ('matcherino_user_id', list(matcherino_ids)),
            )
            if values
        ]
        users: Dict[int, User] = {}
        if clauses:
            for user in await User.filter(Q(*clauses, join_type='OR'), is_active=True, is_system=False):
                users[user.id] = user
        logins = [login.lower() for login in twitch_logins]
        if logins:
            # Stored as Twitch's display name, so compare case-insensitively.
            for user in await User.annotate(twitch_lower=Lower('twitch_username')).filter(
                twitch_lower__in=logins, is_active=True, is_system=False,
            ):
                users[user.id] = user
        return list(users.values())

    @staticmethod
    async def users_with_unverified_handle() -> List[User]:
        """Users who typed a Matcherino handle but have no linked id yet (global)."""
        return await User.filter(
            matcherino_username__isnull=False,
            matcherino_user_id__isnull=True,
            is_active=True,
            is_system=False,
        )

    @staticmethod
    async def user_with_matcherino_id(matcherino_id: str) -> Optional[User]:
        return await User.get_or_none(matcherino_user_id=matcherino_id)
