"""Discord embed builders for notification DMs.

Parallel to :mod:`application.utils.discord_messages` (which produces the
plain-text version). Every notification is *sent* as a Discord embed — a
colour-coded card with a community-name footer and native ``<t:…>`` timestamps
that render in each viewer's own timezone with a live countdown. The plain-text
string still flows through ``send_dm`` for the web-push mirror and the mock, so
this module is purely additive: it never replaces the text, it enriches the
Discord representation.

Kept separate from ``discord_messages`` so the text builders (imported by the
REST layer, tests, etc.) don't pull in ``discord`` just to format a string.
"""

from datetime import datetime
from typing import Optional, Sequence

import discord

# Colour by category / match state (0xRRGGBB). Warm-tuned toward the app's
# phoenix/status palette where it doesn't fight Discord's own semantics.
COLOR_SCHEDULED = 0x5865F2    # blurple — informational / new
COLOR_RESCHEDULED = 0xB45309  # burnt amber — needs attention
COLOR_CHECKED_IN = 0xB45309   # amber — imminent
COLOR_STARTED = 0x557A1F      # olive green — live
COLOR_FINISHED = 0x6B6258     # warm gray — done
COLOR_CONFIRMED = 0x0E7470    # teal — settled
COLOR_STREAM = 0xE0A82E       # gold — highlight
COLOR_CREW = 0x5865F2         # blurple
COLOR_SEED = 0x8250DF         # purple
COLOR_VOLUNTEER = 0x0E7470    # teal

# state_changed transitions → colour
_STATE_COLORS = {
    'Started': COLOR_STARTED,
    'Finished': COLOR_FINISHED,
    'Confirmed': COLOR_CONFIRMED,
}

# A field tuple is (name, value, inline). Empty values are dropped.
Field = tuple


def _players_value(player_names: Optional[Sequence[str]]) -> str:
    """"A vs B" for two, comma-joined otherwise, '' for none."""
    if not player_names:
        return ''
    names = list(player_names)
    if len(names) == 2:
        return ' vs '.join(names)
    return ', '.join(names)


def time_field(when: Optional[datetime]) -> str:
    """A Discord timestamp that renders in the viewer's own timezone plus a live
    relative countdown: ``<t:unix:F> · <t:unix:R>``. '' when ``when`` is None."""
    if when is None:
        return ''
    ts = int(when.timestamp())
    return f"<t:{ts}:F> · <t:{ts}:R>"


def notification_embed(
    *,
    title: str,
    color: int,
    community_name: Optional[str] = None,
    description: Optional[str] = None,
    fields: Optional[Sequence[Field]] = None,
    url: Optional[str] = None,
) -> discord.Embed:
    """The shared card shape: title, colour, optional description, fields, and a
    community-name footer. Fields with an empty value are skipped."""
    embed = discord.Embed(title=title, colour=color)
    if description:
        embed.description = description
    if url:
        embed.url = url
    for name, value, inline in (fields or []):
        if value:
            embed.add_field(name=name, value=value, inline=inline)
    if community_name:
        embed.set_footer(text=community_name)
    return embed


def match_embed(
    *,
    title: str,
    color: int,
    tournament: str,
    community_name: Optional[str] = None,
    player_names: Optional[Sequence[str]] = None,
    when: Optional[datetime] = None,
    stream_room_name: Optional[str] = None,
    description: Optional[str] = None,
    url: Optional[str] = None,
) -> discord.Embed:
    """Embed for a match notification: Tournament / Players / Time / Stage."""
    fields: list[Field] = [('Tournament', tournament, True)]
    players = _players_value(player_names)
    if players:
        fields.append(('Players', players, True))
    if when is not None:
        fields.append(('Time', time_field(when), False))
    if stream_room_name:
        fields.append(('Stage', stream_room_name, True))
    return notification_embed(
        title=title, color=color, community_name=community_name,
        description=description, fields=fields, url=url,
    )


def state_changed_embed(
    tournament: str,
    new_state: str,
    *,
    community_name: Optional[str] = None,
    player_names: Optional[Sequence[str]] = None,
    when: Optional[datetime] = None,
    stream_room_name: Optional[str] = None,
) -> discord.Embed:
    """Started / Finished / Confirmed transition card."""
    emoji = {'Started': '🔴', 'Finished': '🏁', 'Confirmed': '☑️'}.get(new_state, '•')
    return match_embed(
        title=f"{emoji} Match {new_state.lower()}",
        color=_STATE_COLORS.get(new_state, COLOR_SCHEDULED),
        tournament=tournament, community_name=community_name,
        player_names=player_names, when=when, stream_room_name=stream_room_name,
    )


def volunteer_embed(
    *,
    title: str,
    position: str,
    community_name: Optional[str] = None,
    starts: Optional[datetime] = None,
    ends: Optional[datetime] = None,
    description: Optional[str] = None,
) -> discord.Embed:
    """Embed for a volunteer shift: Position / Start / End."""
    fields: list[Field] = [('Position', position, False)]
    if starts is not None:
        fields.append(('Start', time_field(starts), True))
    if ends is not None:
        fields.append(('End', time_field(ends), True))
    return notification_embed(
        title=title, color=COLOR_VOLUNTEER, community_name=community_name,
        description=description, fields=fields,
    )
