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
    'You do not have an Wizzrobe account. Please log in at the website first.'
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
    bracket_line: str = '',
) -> list[str]:
    """Consistent identifying block for a match: round, players, time, stage.

    Omits any line whose data is empty. ``bracket_line`` is the series context
    for a match that is one game of a bracket matchup — "Semifinals · Game 2 of 3
    · Series 1-0" — and leads, because it is the thing that tells a player *what
    this match is for*. Empty for the vast majority of matches, which no bracket
    scheduled.
    """
    lines: list[str] = []
    if bracket_line:
        lines.append(f"Round: {bracket_line}")
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
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
        bracket_line=bracket_line,
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
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=new_scheduled_at_display,
        stream_room_name=stream_room_name,
        time_label='New time',
        bracket_line=bracket_line,
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
    bracket_line: str = '',
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
        bracket_line=bracket_line,
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
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
        bracket_line=bracket_line,
    )
    block = ("\n".join(info) + "\n\n") if info else ''
    return (
        f"Your match in **{tournament_name}** has been checked in.\n\n"
        f"{block}"
        f"The match is about to begin — good luck!"
    )


def cancelled_dm(
    tournament_name: str,
    *,
    reason: str = '',
    player_names: Optional[list[str]] = None,
    scheduled_at_display: str = '',
    stream_room_name: str = '',
    bracket_line: str = '',
    released: bool = False,
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
        time_label='Was scheduled for',
        bracket_line=bracket_line,
    )
    block = ("\n".join(info) + "\n\n") if info else ''
    why = f"{reason}\n\n" if reason else ''
    # A bracket game that was cancelled hands its series slot back (D3), so the
    # matchup is open again and the entrants are the ones who have to rebook it —
    # the opposite of the default "nothing further is needed".
    closing = (
        "This game has been released — the matchup is open to reschedule."
        if released else "Nothing further is needed from you."
    )
    return (
        f"Your match in **{tournament_name}** has been cancelled.\n\n"
        f"{block}"
        f"{why}"
        f"{closing}"
    )


def state_changed_dm(
    tournament_name: str,
    new_state: str,
    *,
    player_names: Optional[list[str]] = None,
    scheduled_at_display: str = '',
    stream_room_name: str = '',
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
        bracket_line=bracket_line,
    )
    block = ("\n\n" + "\n".join(info)) if info else ''
    return f"Your match in **{tournament_name}** is now: **{new_state}**.{block}"


def matchup_ready_dm(
    tournament_name: str,
    round_name: str,
    opponent_name: str,
    *,
    opponent_seed: Optional[int] = None,
    best_of: int = 1,
    schedule_url: str = '',
    rebook: bool = False,
) -> str:
    """The one new bracket notification: "you have a matchup to schedule".

    A DM is sent when it asks the recipient to *do* something, and this is the
    only thing in a bracket that nobody else can do for them —
    ``allow_player_match_requests`` is off for bracket-run tournaments, so the
    bracket is their sole route to booking a time. Advancing and being eliminated
    get no DM: the bracket shows those.

    ``rebook`` is the released-game variant (D3): the matchup was booked, the
    game was called off, and its slot is open again. It says so explicitly rather
    than reading as a duplicate of the first invitation.
    """
    opponent = f"{opponent_name} (#{opponent_seed})" if opponent_seed else opponent_name
    lines = [f"Opponent: {opponent}", f"Round: {round_name}"]
    if best_of > 1:
        lines.append(f"Format: Best of {best_of}")
    body = "\n".join(lines)
    if rebook:
        intro = (
            f"Your **{round_name}** match in **{tournament_name}** was called off, "
            f"and the matchup is open to reschedule."
        )
        action = "Pick a new time"
    else:
        intro = (
            f"Your **{round_name}** matchup in **{tournament_name}** is ready to "
            f"schedule."
        )
        action = "Pick a time"
    call = f"[{action}]({schedule_url})" if schedule_url else f"{action} on the bracket."
    return f"{intro}\n\n{body}\n\n{call}"


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
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stream_room_name=stream_room_name,
        bracket_line=bracket_line,
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
    Blank lines separate the intro, the detail block, and the call to action —
    matching the match-notification rhythm elsewhere in this module.
    """
    players = _players_label(player_names)
    details: list[str] = []
    # Only show the title when it adds information beyond the roster line — some
    # schedule feeds set the match title to the matchup itself, which would
    # otherwise print the same value twice ("Match: A vs B" / "Players: A vs B").
    if match_title and match_title != players:
        details.append(f"**Match:** {match_title}")
    if players:
        details.append(f"**Players:** {players}")
    if scheduled_at_display:
        details.append(f"**Scheduled:** {scheduled_at_display}")
    if stream_room_name:
        details.append(f"**Stage:** {stream_room_name}")
    blocks = [f"You've been approved as {crew_type}."]
    if details:
        blocks.append("\n".join(details))
    blocks.append("Please click below to acknowledge your assignment.")
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Volunteer scheduling
# ---------------------------------------------------------------------------

def _volunteer_shift_lines(
    position_name: str,
    label: Optional[str],
    starts_display: str,
    ends_display: str,
) -> list[str]:
    title = position_name
    if label:
        title = f"{position_name} — {label}"
    lines = [f"**Position:** {title}"]
    if starts_display:
        lines.append(f"**Start:** {starts_display}")
    if ends_display:
        lines.append(f"**End:** {ends_display}")
    return lines


def volunteer_assignment_dm(
    position_name: str,
    label: Optional[str],
    starts_display: str,
    ends_display: str,
) -> str:
    """DM sent when a volunteer is assigned to a shift.

    No community name is hardcoded — the app is multi-tenant, so a fixed org
    label would be wrong for every community but one. Blank lines separate the
    intro, the shift block, and the call to action.
    """
    details = _volunteer_shift_lines(position_name, label, starts_display, ends_display)
    blocks = ["You've been scheduled for a volunteer shift."]
    if details:
        blocks.append("\n".join(details))
    blocks.append("Please click below to acknowledge your shift.")
    return "\n\n".join(blocks)


def volunteer_reminder_dm(
    position_name: str,
    label: Optional[str],
    starts_display: str,
    ends_display: str,
) -> str:
    """Reminder DM sent ahead of a volunteer shift."""
    details = _volunteer_shift_lines(position_name, label, starts_display, ends_display)
    blocks = ["⏰ Reminder: you have an upcoming volunteer shift."]
    if details:
        blocks.append("\n".join(details))
    blocks.append("Please click below to acknowledge your shift.")
    return "\n\n".join(blocks)


def volunteer_ack_confirmation(position_name: str) -> str:
    return f"Thanks! Your **{position_name}** shift is acknowledged."


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
