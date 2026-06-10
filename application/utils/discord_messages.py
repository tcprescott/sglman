"""
Discord Message Templates

All Discord DM and ephemeral message text lives here. Import individual
builder functions and constants where needed; do not inline message text
in service or handler code.

Messages never expose raw match ID numbers — they are meaningless to
recipients. A match is identified by the players involved, the scheduled
time, and the stage (when assigned).
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Shared error constants (used in multiple handlers)
# ---------------------------------------------------------------------------

MSG_NO_ACCOUNT = (
    'You do not have an SGL On Site account. Please log in at the website first.'
)
MSG_UNEXPECTED_ERROR_MATCH = (
    'An unexpected error occurred. Please try again or use the website to acknowledge.'
)
MSG_UNEXPECTED_ERROR_CREW = (
    'An unexpected error occurred. Please try again or use the website to acknowledge.'
)


# ---------------------------------------------------------------------------
# Shared formatting helpers
# ---------------------------------------------------------------------------

def _players_label(player_names: Optional[list[str]]) -> str:
    """Human-readable list of players: "A vs B" for two, comma-joined otherwise."""
    if not player_names:
        return ''
    if len(player_names) == 2:
        return ' vs '.join(player_names)
    return ', '.join(player_names)


def _match_info_lines(
    *,
    player_names: Optional[list[str]] = None,
    scheduled_at_display: str = '',
    stream_room_name: str = '',
    time_label: str = 'Scheduled for',
) -> list[str]:
    """Consistent identifying block for a match: players, time, stage.

    Omits any line whose data is empty.
    """
    lines: list[str] = []
    players = _players_label(player_names)
    if players:
        lines.append(f"Players: {players}")
    if scheduled_at_display:
        lines.append(f"{time_label}: {scheduled_at_display}")
    if stream_room_name:
        lines.append(f"Stage: {stream_room_name}")
    return lines


# ---------------------------------------------------------------------------
# Match scheduling DMs  (sent by MatchScheduleService / MatchService)
# ---------------------------------------------------------------------------

def scheduled_dm(
    tournament_name: str,
    scheduled_at_display: str,
    *,
    player_names: Optional[list[str]] = None,
    stream_room_name: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
    )
    body = "\n".join(info)
    return (
        f"A match has been scheduled for you in **{tournament_name}**.\n\n"
        f"{body}\n\n"
        f"Good luck!"
    )


def rescheduled_dm(
    tournament_name: str,
    new_scheduled_at_display: str,
    *,
    player_names: Optional[list[str]] = None,
    stream_room_name: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=new_scheduled_at_display,
        stream_room_name=stream_room_name,
        time_label='New time',
    )
    body = "\n".join(info)
    return (
        f"Your match in **{tournament_name}** has been rescheduled.\n\n"
        f"{body}\n\n"
        f"Please update your calendar."
    )


def acknowledgment_request_dm(
    tournament_name: str,
    scheduled_at_display: str,
    *,
    rescheduled: bool,
    stream_room_name: str = '',
    player_names: Optional[list[str]] = None,
) -> str:
    if rescheduled:
        intro = f"Your match in **{tournament_name}** has been rescheduled."
        time_label = 'New time'
    else:
        intro = f"A match has been scheduled for you in **{tournament_name}**."
        time_label = 'Scheduled for'
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
        time_label=time_label,
    )
    body = "\n".join(info)
    return (
        f"{intro}\n\n"
        f"{body}\n\n"
        f"Click **Acknowledge** below to confirm you've seen this."
    )


def checked_in_dm(
    tournament_name: str,
    *,
    player_names: Optional[list[str]] = None,
    scheduled_at_display: str = '',
    stream_room_name: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
    )
    block = ("\n".join(info) + "\n\n") if info else ''
    return (
        f"Your match in **{tournament_name}** has been checked in.\n\n"
        f"{block}"
        f"The match is about to begin — good luck!"
    )


def state_changed_dm(
    tournament_name: str,
    new_state: str,
    *,
    player_names: Optional[list[str]] = None,
    scheduled_at_display: str = '',
    stream_room_name: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
    )
    block = ("\n\n" + "\n".join(info)) if info else ''
    return f"Your match in **{tournament_name}** is now: **{new_state}**.{block}"


def stream_candidate_dm(
    tournament_name: str,
    scheduled_at_display: str,
    *,
    player_names: Optional[list[str]] = None,
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
    )
    body = "\n".join(info)
    return (
        f"A match in **{tournament_name}** has been flagged as a potential stream match!\n\n"
        f"{body}\n\n"
        f"Use the buttons below to sign up as crew."
    )


def seed_dm(
    player_name: str,
    tournament_name: str,
    seed_url: str,
    *,
    player_names: Optional[list[str]] = None,
    scheduled_at_display: str = '',
    stream_room_name: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
    )
    block = ("\n".join(info) + "\n\n") if info else ''
    return (
        f"Hello {player_name},\n\n"
        f"A seed has been generated for your upcoming match in **{tournament_name}**.\n\n"
        f"{block}"
        f"{seed_url}\n\n"
        f"Good luck and have fun!"
    )


# ---------------------------------------------------------------------------
# Crew assignment DMs  (sent by CrewService)
# ---------------------------------------------------------------------------

def crew_assignment_dm(
    crew_type: str,
    match_title: Optional[str],
    scheduled_at_display: str,
    stream_room_name: Optional[str],
    player_names: Optional[list[str]],
) -> str:
    """DM with crew-acknowledgment button sent when a crew member is approved.

    Pass None or '' for optional fields to suppress them from the message.
    """
    lines = [f"You've been approved as {crew_type}."]
    if match_title:
        lines.append(f"**Match:** {match_title}")
    players = _players_label(player_names)
    if players:
        lines.append(f"**Players:** {players}")
    if scheduled_at_display:
        lines.append(f"**Scheduled:** {scheduled_at_display}")
    if stream_room_name:
        lines.append(f"**Stage:** {stream_room_name}")
    lines.append("Please click below to acknowledge your assignment.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Match acknowledgment ephemeral replies  (discordbot/match_acknowledgment.py)
# ---------------------------------------------------------------------------

def match_ack_confirmation(player_names: str) -> str:
    """Ephemeral success reply after a user clicks the match Acknowledge button."""
    if player_names:
        return f'You have acknowledged your match ({player_names}). Thanks!'
    return 'You have acknowledged your match. Thanks!'


# ---------------------------------------------------------------------------
# Crew acknowledgment ephemeral replies  (discordbot/crew_acknowledgment.py)
# ---------------------------------------------------------------------------

def crew_ack_confirmation(crew_type: str, player_names: str) -> str:
    """Ephemeral success reply after a user clicks the crew Acknowledge button."""
    if player_names:
        return (
            f'You have acknowledged your {crew_type} assignment '
            f'({player_names}). Thanks!'
        )
    return f'You have acknowledged your {crew_type} assignment. Thanks!'


# ---------------------------------------------------------------------------
# Crew signup ephemeral replies  (discordbot/crew_signup.py)
# ---------------------------------------------------------------------------

def crew_signup_confirmation(role: str, player_names: str) -> str:
    """Ephemeral success reply after a user signs up for crew via a DM button."""
    match_ref = f' for the match ({player_names})' if player_names else ''
    return (
        f'You have been signed up as a **{role}**{match_ref}. '
        f'Awaiting admin approval.'
    )


# ---------------------------------------------------------------------------
# Unwatch ephemeral replies  (discordbot/watch_buttons.py)
# ---------------------------------------------------------------------------

def unwatch_confirmation(player_names: str, was_watching: bool) -> str:
    """Ephemeral reply after a user clicks the Unwatch button on a match DM."""
    match_ref = f' ({player_names})' if player_names else ''
    if was_watching:
        return f'You are no longer watching the match{match_ref}.'
    return f'You were not watching the match{match_ref}.'
