"""
Discord Message Templates

All Discord DM and ephemeral message text lives here. Import individual
builder functions and constants where needed; do not inline message text
in service or handler code.

Messages never expose raw match ID numbers — they are meaningless to
recipients. A match is identified by the players involved, the scheduled
time, and the stage (when assigned).

This module holds the match lifecycle. Every other domain has a sibling of its
own, all of them moved out as this module kept crossing the 800-line budget:
:mod:`~application.utils.discord_messages_crew` (crew assignment),
:mod:`~application.utils.discord_messages_volunteer` (volunteer shifts),
:mod:`~application.utils.discord_messages_qualifier` (async qualifiers),
:mod:`~application.utils.discord_messages_reschedule` (reschedule requests) and
:mod:`~application.utils.discord_messages_tenant` (community join requests).
"""

from typing import NamedTuple, Optional

from application.utils.match_labels import players_label


class DMLink(NamedTuple):
    """A one-click route out of a notification: a button label and where it goes.

    Every DM that asks the recipient to *do* something carries one. ``send_dm``
    renders it as a Discord link button and hands the same URL to the web-push
    mirror as its tap target, so the ask is one press away on either surface —
    rather than a sentence naming a page the reader then has to go find.

    ``url`` must be absolute: a DM is read outside any request context, so a bare
    ``/home/player`` would resolve against nothing. Build them with
    :mod:`application.services.notification_links`.
    """

    label: str
    url: str


# ---------------------------------------------------------------------------
# Shared error constants (used in multiple handlers)
# ---------------------------------------------------------------------------

MSG_NO_ACCOUNT = (
    "You don't have a Wizzrobe account yet. Log in at the website first and "
    "this will work."
)


def msg_unexpected_error(action: str = 'finish this') -> str:
    """Standard fallback text for a failed Discord button interaction.

    ``action`` names what the website can still do instead of the button —
    "acknowledge", "sign up" — falling back to a generic phrase for
    interactions with no single verb (e.g. unwatch).
    """
    return f"Something went wrong. Try again in a moment, or {action} on the website."


MSG_UNEXPECTED_ERROR = msg_unexpected_error()


# ---------------------------------------------------------------------------
# Shared formatting helpers
# ---------------------------------------------------------------------------

# Shared with the web copy, which identifies a match the same way — see
# application/utils/match_labels.py.
_players_label = players_label


def _match_info_lines(
    *,
    player_names: Optional[list[str]] = None,
    scheduled_at_display: str = '',
    stage_name: str = '',
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
    if stage_name:
        lines.append(f"Stage: {stage_name}")
    return lines


# ---------------------------------------------------------------------------
# Match scheduling DMs  (sent by MatchScheduleService / MatchService)
# ---------------------------------------------------------------------------

def scheduled_dm(
    tournament_name: str,
    scheduled_at_display: str,
    *,
    player_names: Optional[list[str]] = None,
    stage_name: str = '',
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stage_name=stage_name,
        bracket_line=bracket_line,
    )
    body = "\n".join(info)
    return (
        f"You've got a match scheduled in **{tournament_name}**.\n\n"
        f"{body}\n\n"
        f"Good luck!"
    )


def rescheduled_dm(
    tournament_name: str,
    new_scheduled_at_display: str,
    *,
    player_names: Optional[list[str]] = None,
    stage_name: str = '',
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=new_scheduled_at_display,
        stage_name=stage_name,
        time_label='New time',
        bracket_line=bracket_line,
    )
    body = "\n".join(info)
    return (
        f"Your match in **{tournament_name}** got moved. Here's the new time.\n\n"
        f"{body}\n\n"
        f"Make sure it's on your calendar."
    )


def acknowledgment_request_dm(
    tournament_name: str,
    scheduled_at_display: str,
    *,
    rescheduled: bool,
    stage_name: str = '',
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
        stage_name=stage_name,
        time_label=time_label,
        bracket_line=bracket_line,
    )
    body = "\n".join(info)
    return (
        f"{intro}\n\n"
        f"{body}\n\n"
        f"Click **Acknowledge** below to confirm you've seen this."
    )


# ---------------------------------------------------------------------------
# Stage DMs  (sent by MatchService.assign_stage and the stage reminder worker)
# ---------------------------------------------------------------------------
# The information a runner needs is the substitution: this match happens on a
# stage instead of in the tournament room. Say that, not "a stage has been
# assigned", which describes a database row rather than where to walk.

def _stage_info_lines(
    player_names: Optional[list[str]], scheduled_at_display: str,
) -> str:
    """Players and time for a stage DM, with the stage left out of the block.

    The stage is the headline of all three messages, so a ``Stage:`` line
    underneath would say the same thing twice.
    """
    return "\n".join(_match_info_lines(
        player_names=player_names, scheduled_at_display=scheduled_at_display,
    ))


def stage_assigned_dm(
    tournament_name: str,
    stage_name: str,
    scheduled_at_display: str,
    *,
    player_names: Optional[list[str]] = None,
) -> str:
    """"You're on Kraid" — sent the moment a stage is assigned.

    Where to go is the whole message, so it states the substitution outright:
    the stage, not the tournament room.
    """
    body = _stage_info_lines(player_names, scheduled_at_display)
    block = f"{body}\n\n" if body else ''
    return (
        f"Your match in **{tournament_name}** is on **{stage_name}**.\n\n"
        f"{block}"
        f"Play it at the stage rather than in the tournament room."
    )


def stage_cleared_dm(
    tournament_name: str,
    scheduled_at_display: str,
    *,
    player_names: Optional[list[str]] = None,
) -> str:
    """The retraction. Telling someone they're on a stage and never taking it
    back sends them to an empty one."""
    body = _stage_info_lines(player_names, scheduled_at_display)
    block = f"{body}\n\n" if body else ''
    return (
        f"Your match in **{tournament_name}** is off the stage.\n\n"
        f"{block}"
        f"Play it in the tournament room as usual."
    )


def stage_reminder_dm(
    tournament_name: str,
    stage_name: str,
    scheduled_at_display: str,
    *,
    player_names: Optional[list[str]] = None,
) -> str:
    """The nudge shortly before the match, naming the stage and the time again.

    The assignment DM may have arrived hours ago and two matches back.
    """
    body = _stage_info_lines(player_names, scheduled_at_display)
    block = f"{body}\n\n" if body else ''
    return (
        f"Your match in **{tournament_name}** is coming up on **{stage_name}**.\n\n"
        f"{block}"
        f"Head to the stage rather than the tournament room."
    )


def checked_in_dm(
    tournament_name: str,
    *,
    player_names: Optional[list[str]] = None,
    scheduled_at_display: str = '',
    stage_name: str = '',
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stage_name=stage_name,
        bracket_line=bracket_line,
    )
    block = ("\n".join(info) + "\n\n") if info else ''
    return (
        f"You're checked in for your match in **{tournament_name}**.\n\n"
        f"{block}"
        f"The match is about to begin — good luck!"
    )


def cancelled_dm(
    tournament_name: str,
    *,
    reason: str = '',
    player_names: Optional[list[str]] = None,
    scheduled_at_display: str = '',
    stage_name: str = '',
    bracket_line: str = '',
    released: bool = False,
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stage_name=stage_name,
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
        if released else "You're all set. Nothing else to do here."
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
    stage_name: str = '',
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stage_name=stage_name,
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
    ``allow_player_match_requests`` is off for bracket-run tournaments, so this is
    their sole route to booking a time. Advancing and being eliminated get no DM:
    the bracket shows those.

    ``rebook`` is the released-game variant (D3): the matchup was booked, the
    game was called off, and its slot is open again. It says so explicitly rather
    than reading as a duplicate of the first invitation.

    ``schedule_url`` opens the picker itself (``/home/player?schedule=<id>``), not
    the bracket page: the bracket's Schedule button is staff-only, so the two
    people this DM addresses could never have used it.
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
    call = (
        f"[{action}]({schedule_url})" if schedule_url
        else f"{action} on the Player tab of your community's site."
    )
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
        f"A match in **{tournament_name}** might be heading to stream!\n\n"
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
    stage_name: str = '',
    bracket_line: str = '',
) -> str:
    info = _match_info_lines(
        player_names=player_names,
        scheduled_at_display=scheduled_at_display,
        stage_name=stage_name,
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
# Match acknowledgment ephemeral replies  (discordbot/match_acknowledgment.py)
# ---------------------------------------------------------------------------

def match_ack_confirmation(player_names: str) -> str:
    """Ephemeral success reply after a user clicks the match Acknowledge button."""
    if player_names:
        return f"You've acknowledged your match ({player_names}). Thanks!"
    return "You've acknowledged your match. Thanks!"


# ---------------------------------------------------------------------------
# Unwatch ephemeral replies  (discordbot/watch_buttons.py)
# ---------------------------------------------------------------------------

def unwatch_confirmation(player_names: str, was_watching: bool) -> str:
    """Ephemeral reply after a user clicks the Unwatch button on a match DM."""
    match_ref = f' ({player_names})' if player_names else ''
    if was_watching:
        return f'You are no longer watching the match{match_ref}.'
    return f'You were not watching the match{match_ref}.'
