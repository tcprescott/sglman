"""
Discord Message Templates: player reschedule requests

The DM copy for :mod:`application.services.match_reschedule_service` — the ask
to staff, the nudge to the opponent, and the answer back to the requester.

A sibling of :mod:`application.utils.discord_messages` rather than more lines in
it: that module was already the largest file under ``application/utils`` and sat
just under the length budget, so a new domain of its own goes in its own file.
The convention is otherwise identical — all Discord text lives in a builder, and
none of it is inlined in service or handler code.

Times arrive as **display strings** already rendered by
``discord_embeds.time_field``, so each recipient's client localises them. Never
pass a formatted datetime.
"""

from typing import Optional


def _reschedule_ask_lines(
    *,
    kind_cancel: bool,
    current_display: str,
    proposed_display: str,
    reason: str,
) -> list[str]:
    """The three lines every reschedule DM shares: from, to, and why."""
    lines = [f"**Currently:** {current_display}"]
    if kind_cancel:
        lines.append("**Asking to:** call the match off")
    elif proposed_display:
        lines.append(f"**Proposed:** {proposed_display}")
    else:
        lines.append("**Proposed:** no specific time — they just can't make this one")
    if reason:
        lines.append(f"**Reason:** {reason}")
    return lines


def reschedule_requested_dm(
    tournament_name: str,
    requester_name: str,
    *,
    kind_cancel: bool,
    current_display: str,
    proposed_display: str = '',
    reason: str = '',
    player_names: Optional[list[str]] = None,
    opponent_agreed: bool = False,
) -> str:
    """To staff: someone wants their match moved or called off."""
    verb = 'called off' if kind_cancel else 'moved'
    lines = _reschedule_ask_lines(
        kind_cancel=kind_cancel, current_display=current_display,
        proposed_display=proposed_display, reason=reason,
    )
    if player_names:
        lines.insert(0, f"**Match:** {' vs '.join(player_names)}")
    if opponent_agreed:
        lines.append("**Opponent:** has agreed")
    body = "\n".join(lines)
    return (
        f"**{requester_name}** asked for a match in **{tournament_name}** to be {verb}.\n\n"
        f"{body}\n\n"
        f"Nothing has changed yet — approving it is what moves the match."
    )


def reschedule_opponent_dm(
    tournament_name: str,
    requester_name: str,
    *,
    kind_cancel: bool,
    current_display: str,
    proposed_display: str = '',
    reason: str = '',
) -> str:
    """To the other player: your opponent asked, do you agree?

    Agreement is a signal for staff, not a veto, and the copy says so — a button
    that reads like a decision and turns out to be advice is worse than no button.
    """
    verb = 'call off' if kind_cancel else 'move'
    lines = _reschedule_ask_lines(
        kind_cancel=kind_cancel, current_display=current_display,
        proposed_display=proposed_display, reason=reason,
    )
    body = "\n".join(lines)
    return (
        f"**{requester_name}** asked staff to {verb} your match in "
        f"**{tournament_name}**.\n\n"
        f"{body}\n\n"
        f"Press **Agree** if that works for you. Staff still make the call, but "
        f"knowing you're both happy saves them asking."
    )


def reschedule_decided_dm(
    tournament_name: str,
    *,
    approved: bool,
    kind_cancel: bool,
    new_display: str = '',
    note: str = '',
) -> str:
    """To the requester, once staff have answered."""
    if approved:
        if kind_cancel:
            intro = f"Your match in **{tournament_name}** has been called off, as you asked."
        elif new_display:
            intro = (
                f"Staff moved your match in **{tournament_name}**.\n\n"
                f"**New time:** {new_display}"
            )
        else:
            intro = f"Staff approved your request for **{tournament_name}**."
    else:
        intro = (
            f"Staff couldn't do the change you asked for in **{tournament_name}**. "
            f"Your match is unchanged."
        )
    body = f"{intro}\n\n**They said:** {note}" if note else intro
    tail = (
        "" if approved
        else "\n\nYou can ask again with a different time if that helps."
    )
    return f"{body}{tail}"


def reschedule_agree_confirmation(requester_name: str) -> str:
    """Ephemeral reply on the opponent's Agree button."""
    return (
        f"Thanks — staff will see that you're happy with {requester_name}'s "
        f"request. They still decide, so watch for the result."
    )
