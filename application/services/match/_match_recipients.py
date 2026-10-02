"""Shared DM-recipient resolution for a match.

``collect_match_recipients`` is needed both by the lifecycle half of
``match_schedule_service`` and by the notification mixin split out of it, so it
lives here rather than in either — keeping the two modules free of a cycle.
"""

from typing import NamedTuple

from application.tenant_context import require_tenant_id
from application.utils.discord_messages import (
    AUDIENCE_CREW,
    AUDIENCE_PLAYER,
    AUDIENCE_WATCHER,
)
from models import Commentator, Match, MatchPlayers, MatchWatcher, Tracker, User


class MatchRecipient(NamedTuple):
    """Why one person is hearing about a match, and whether they get Unwatch.

    ``audience`` is the strongest tie they have to it — player, then crew, then
    watcher — because that decides what the copy can truthfully say ("your
    match" is only true for a player) and where its button can send them.
    ``is_watcher`` is independent: a player who also watches still gets the
    Unwatch button they asked for.
    """

    audience: str
    is_watcher: bool


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
    """``{discord_id: is_watcher}`` — :func:`collect_match_audience` without the audience."""
    audience = await collect_match_audience(
        match,
        include_players=include_players,
        include_watchers=include_watchers,
        exclude_players=exclude_players,
        require_opt_in=require_opt_in,
    )
    return {discord_id: r.is_watcher for discord_id, r in audience.items()}


async def collect_match_audience(
    match: Match,
    *,
    include_players: bool = True,
    include_watchers: bool = True,
    exclude_players: bool = False,
    require_opt_in: bool = True,
) -> dict[int, MatchRecipient]:
    """Return ``{discord_id: MatchRecipient}`` for a match's DM recipients.

    Players, approved commentators, and approved trackers are collected as
    non-watchers; a watcher flips ``is_watcher`` on (they get the unwatch-button
    DM) without demoting a player or crew member's audience. Insertion order is
    players → commentators → trackers → watchers, and each discord_id appears
    once.

    - ``include_players``: add players to the recipient set.
    - ``include_watchers``: add match watchers (with the watcher flag).
    - ``exclude_players``: drop any crew/watcher who is also a player (used by the
      crew notification, where players get a separate acknowledgment DM).
    - ``require_opt_in``: honor each user's ``dm_notifications`` opt-out. Set
      ``False`` for the subscriber-dedup pass, which only needs the ids.
    """
    tenant_id = require_tenant_id()
    recipients: dict[int, MatchRecipient] = {}

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
                recipients.setdefault(
                    mp.user.discord_id, MatchRecipient(AUDIENCE_PLAYER, False),
                )

    commentators = await Commentator.filter(
        match=match, approved=True, tenant_id=tenant_id
    ).prefetch_related('user')
    for c in commentators:
        if _dm_opt_ok(c.user, require_opt_in=require_opt_in) and not _blocked(c.user):
            recipients.setdefault(c.user.discord_id, MatchRecipient(AUDIENCE_CREW, False))

    trackers = await Tracker.filter(
        match=match, approved=True, tenant_id=tenant_id
    ).prefetch_related('user')
    for t in trackers:
        if _dm_opt_ok(t.user, require_opt_in=require_opt_in) and not _blocked(t.user):
            recipients.setdefault(t.user.discord_id, MatchRecipient(AUDIENCE_CREW, False))

    if include_watchers:
        watchers = await MatchWatcher.filter(
            match=match, tenant_id=tenant_id
        ).prefetch_related('user')
        for w in watchers:
            if _dm_opt_ok(w.user, require_opt_in=require_opt_in) and not _blocked(w.user):
                held = recipients.get(w.user.discord_id)
                recipients[w.user.discord_id] = MatchRecipient(
                    held.audience if held else AUDIENCE_WATCHER, True,
                )

    return recipients

