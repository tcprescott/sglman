"""Matching check-in rows to Wizzrobe accounts, and what a match writes back.

:func:`build_lookups` finds the candidate accounts for a set of roster rows by
exact identifier; ``check_in_rules.resolve_link`` picks among them.
:func:`remember_matcherino_account` / :func:`forget_matcherino_account` record
and undo the Matcherino account on a ``User`` when a row is linked or unlinked.
"""

from typing import Dict, Sequence

from application.repositories import CheckInUserLookupRepository, UserRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.check_in_rules import IdentityLookups, handle_id
from models import CheckInEntrant, CheckInLinkMethod, User


async def build_lookups(rows: Sequence[CheckInEntrant]) -> IdentityLookups:
    """Candidate accounts for ``rows``, indexed by each exact identifier."""
    discord_ids = {
        int(row.auth_id) for row in rows
        if row.auth_provider == 'discord' and (row.auth_id or '').isdigit()
    }
    twitch_ids = {row.auth_id for row in rows if row.auth_provider == 'twitch' and row.auth_id}
    matcherino_ids = {row.matcherino_user_id for row in rows if row.matcherino_user_id}
    users = await CheckInUserLookupRepository.users_by_identifiers(
        discord_ids=discord_ids, twitch_ids=twitch_ids, matcherino_ids=matcherino_ids,
    )
    lookups = IdentityLookups()
    for user in users:
        if user.matcherino_user_id:
            lookups.by_matcherino_id[user.matcherino_user_id] = user
        if user.discord_id is not None:
            lookups.by_discord_id[str(user.discord_id)] = user
        if user.twitch_user_id:
            lookups.by_twitch_id[user.twitch_user_id] = user
    if matcherino_ids - set(lookups.by_matcherino_id):
        for user in await CheckInUserLookupRepository.users_with_unverified_handle():
            hid = handle_id(user.matcherino_username)
            if hid in matcherino_ids:
                lookups.by_handle_id.setdefault(hid, user)
    return lookups


async def remember_matcherino_account(
    audit_service: AuditService, actor: User, user: User, entrant: CheckInEntrant,
    method: CheckInLinkMethod,
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
        holder = await CheckInUserLookupRepository.user_with_matcherino_id(entrant.matcherino_user_id)
        if holder is None:
            fields['matcherino_user_id'] = entrant.matcherino_user_id
    if not user.matcherino_username:
        fields['matcherino_username'] = f'{entrant.display_name}#{entrant.matcherino_user_id}'
    if not fields:
        return
    await UserRepository.update(user, **fields)
    await audit_service.write_log(
        actor, AuditActions.USER_PROFILE_UPDATED,
        {'user_id': user.id, 'source': 'check_in', 'entrant_id': entrant.id,
         'link_method': method.value, 'changed': fields},
    )


async def forget_matcherino_account(
    audit_service: AuditService, actor: User, user: User, entrant: CheckInEntrant,
) -> None:
    """Undo what :func:`remember_matcherino_account` recorded for this account.

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
    await audit_service.write_log(
        actor, AuditActions.USER_PROFILE_UPDATED,
        {'user_id': user.id, 'source': 'check_in', 'entrant_id': entrant.id,
         'changed': fields},
    )
