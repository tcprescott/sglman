"""Shared DM-recipient resolution for a match.

``collect_match_recipients`` is needed both by the lifecycle half of
``match_schedule_service`` and by the notification mixin split out of it, so it
lives here rather than in either — keeping the two modules free of a cycle.
"""

from application.tenant_context import require_tenant_id
from models import Commentator, Match, MatchPlayers, MatchWatcher, Tracker, User


def _dm_opt_ok(user: User, *, require_opt_in: bool) -> bool:
    """Whether a user can receive a DM: has a discord_id and (if required) opts in."""
    return bool(user.discord_id) and (not require_opt_in or user.dm_notifications)


async def collect_match_recipients(
    match: Match,
    *,
    include_players: bool = True,
    include_watchers: bool = True,
    exclude_players: bool = False,
    require_opt_in: bool = True,
) -> dict[int, bool]:
    """Return ``{discord_id: is_watcher}`` for a match's DM recipients.

    Players, approved commentators, and approved trackers are collected as
    non-watchers (``False``); watchers override to ``True`` (they get the
    unwatch-button DM). Insertion order is players → commentators → trackers →
    watchers, and each discord_id appears once.

    - ``include_players``: add players to the recipient set.
    - ``include_watchers``: add match watchers (with the watcher flag).
    - ``exclude_players``: drop any crew/watcher who is also a player (used by the
      crew notification, where players get a separate acknowledgment DM).
    - ``require_opt_in``: honor each user's ``dm_notifications`` opt-out. Set
      ``False`` for the subscriber-dedup pass, which only needs the ids.
    """
    tenant_id = require_tenant_id()
    recipients: dict[int, bool] = {}

    players = await MatchPlayers.filter(
        match=match, tenant_id=tenant_id
    ).prefetch_related('user')
    player_discord_ids: set[int] = {
        mp.user.discord_id for mp in players if mp.user.discord_id
    }

    def _blocked(user: User) -> bool:
        return exclude_players and user.discord_id in player_discord_ids

    if include_players:
        for mp in players:
            if _dm_opt_ok(mp.user, require_opt_in=require_opt_in):
                recipients.setdefault(mp.user.discord_id, False)

    commentators = await Commentator.filter(
        match=match, approved=True, tenant_id=tenant_id
    ).prefetch_related('user')
    for c in commentators:
        if _dm_opt_ok(c.user, require_opt_in=require_opt_in) and not _blocked(c.user):
            recipients.setdefault(c.user.discord_id, False)

    trackers = await Tracker.filter(
        match=match, approved=True, tenant_id=tenant_id
    ).prefetch_related('user')
    for t in trackers:
        if _dm_opt_ok(t.user, require_opt_in=require_opt_in) and not _blocked(t.user):
            recipients.setdefault(t.user.discord_id, False)

    if include_watchers:
        watchers = await MatchWatcher.filter(
            match=match, tenant_id=tenant_id
        ).prefetch_related('user')
        for w in watchers:
            if _dm_opt_ok(w.user, require_opt_in=require_opt_in) and not _blocked(w.user):
                recipients[w.user.discord_id] = True

    return recipients

