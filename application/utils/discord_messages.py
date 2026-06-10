"""
Discord Message Templates

All Discord DM and ephemeral message text lives here. Import individual
builder functions and constants where needed; do not inline message text
in service or handler code.
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
# Match scheduling DMs  (sent by MatchScheduleService / MatchService)
# ---------------------------------------------------------------------------

def scheduled_dm(
    match_id: int,
    tournament_name: str,
    scheduled_at_display: str,
) -> str:
    return (
        f"A match has been scheduled for you in **{tournament_name}**.\n\n"
        f"Match ID: {match_id}\n"
        f"Scheduled for: {scheduled_at_display}\n\n"
        f"Good luck!"
    )


def rescheduled_dm(
    match_id: int,
    tournament_name: str,
    new_scheduled_at_display: str,
) -> str:
    return (
        f"Your match in **{tournament_name}** has been rescheduled.\n\n"
        f"Match ID: {match_id}\n"
        f"New time: {new_scheduled_at_display}\n\n"
        f"Please update your calendar."
    )


def acknowledgment_request_dm(
    match_id: int,
    tournament_name: str,
    scheduled_at_display: str,
    *,
    rescheduled: bool,
    stream_room_name: str = '',
    player_names: Optional[list[str]] = None,
) -> str:
    if rescheduled:
        details = (
            f"Your match in **{tournament_name}** has been rescheduled.\n\n"
            f"Match ID: {match_id}\n"
            f"New time: {scheduled_at_display}"
        )
    else:
        details = (
            f"A match has been scheduled for you in **{tournament_name}**.\n\n"
            f"Match ID: {match_id}\n"
            f"Scheduled for: {scheduled_at_display}"
        )
    if stream_room_name:
        details += f"\nStream Room: {stream_room_name}"
    if player_names:
        details += f"\nPlayers: {', '.join(player_names)}"
    return (
        f"{details}\n\n"
        f"Click **Acknowledge** below to confirm you've seen this."
    )


def checked_in_dm(
    match_id: int,
    tournament_name: str,
) -> str:
    return (
        f"Match ID {match_id} in **{tournament_name}** has been checked in. "
        f"The match is about to begin — good luck!"
    )


def state_changed_dm(
    match_id: int,
    tournament_name: str,
    new_state: str,
) -> str:
    return f"Match ID {match_id} in **{tournament_name}** is now: **{new_state}**."


def stream_candidate_dm(
    match_id: int,
    tournament_name: str,
    scheduled_at_display: str,
) -> str:
    return (
        f"Match ID {match_id} in **{tournament_name}** has been flagged as a potential stream match!\n\n"
        f"Scheduled for: {scheduled_at_display}\n\n"
        f"Use the buttons below to sign up as crew."
    )


def seed_dm(
    player_name: str,
    match_id: int,
    tournament_name: str,
    seed_url: str,
) -> str:
    return (
        f"Hello {player_name},\n\n"
        f"A seed has been generated for your upcoming match (ID: {match_id}) "
        f"in the tournament '{tournament_name}'.\n\n"
        f"{seed_url}\n\n"
        f"Good luck and have fun!"
    )


# ---------------------------------------------------------------------------
# Crew assignment DMs  (sent by CrewService)
# ---------------------------------------------------------------------------

def crew_assignment_dm(
    crew_type: str,
    match_id: int,
    match_title: Optional[str],
    scheduled_at_display: str,
    stream_room_name: Optional[str],
    player_names: Optional[list[str]],
) -> str:
    """DM with crew-acknowledgment button sent when a crew member is approved.

    Pass None or '' for optional fields to suppress them from the message.
    """
    lines = [f"You've been approved as {crew_type} for Match ID {match_id}."]
    if match_title:
        lines.append(f"**Match:** {match_title}")
    if scheduled_at_display:
        lines.append(f"**Scheduled:** {scheduled_at_display}")
    if stream_room_name:
        lines.append(f"**Stream Room:** {stream_room_name}")
    if player_names:
        lines.append(f"**Players:** {', '.join(player_names)}")
    lines.append("Please click below to acknowledge your assignment.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Match acknowledgment ephemeral replies  (discordbot/match_acknowledgment.py)
# ---------------------------------------------------------------------------

def match_ack_confirmation(match_id: int, player_names: str) -> str:
    """Ephemeral success reply after a user clicks the match Acknowledge button."""
    msg = f'You have acknowledged Match ID {match_id}.'
    if player_names:
        msg += f' Players: {player_names}.'
    msg += ' Thanks!'
    return msg


# ---------------------------------------------------------------------------
# Crew acknowledgment ephemeral replies  (discordbot/crew_acknowledgment.py)
# ---------------------------------------------------------------------------

def crew_ack_confirmation(crew_type: str, match_id: int, player_names: str) -> str:
    """Ephemeral success reply after a user clicks the crew Acknowledge button."""
    msg = f'You have acknowledged your {crew_type} assignment for Match ID {match_id}.'
    if player_names:
        msg += f' Players: {player_names}.'
    msg += ' Thanks!'
    return msg
