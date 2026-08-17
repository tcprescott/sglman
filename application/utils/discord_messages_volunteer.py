"""Discord Message Templates: volunteer shifts

The DM copy for ``application/services/volunteer/`` — the shift a coordinator
scheduled, the reminder before it, the removal, the move, the hand-back to the
coordinators, and the ephemeral reply
``discordbot/volunteer_acknowledgment.py`` sends after the button.

A sibling of :mod:`application.utils.discord_messages` rather than more lines in
it, on the same rule the qualifier and reschedule copy already follow: volunteer
scheduling is a domain of its own, and the parent module holds the match
lifecycle. The convention is otherwise identical — all Discord text lives in a
builder, and none of it is inlined in service or handler code.

Times arrive as **display strings** already rendered by
``discord_embeds.time_field``, so each recipient's client localises them.
"""

from typing import Optional


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


def volunteer_unassigned_dm(
    position_name: str,
    label: Optional[str],
    starts_display: str,
    ends_display: str,
) -> str:
    """DM sent when a coordinator takes a volunteer off a shift.

    No acknowledgment button: there is nothing for them to confirm, and the point
    is that the removal stops being silent.
    """
    details = _volunteer_shift_lines(position_name, label, starts_display, ends_display)
    blocks = ["You have been taken off a volunteer shift."]
    if details:
        blocks.append("\n".join(details))
    blocks.append("No action needed. Ask your coordinator if this looks wrong.")
    return "\n\n".join(blocks)


def volunteer_shift_changed_dm(
    position_name: str,
    label: Optional[str],
    starts_display: str,
    ends_display: str,
    old_starts_display: str = "",
    old_ends_display: str = "",
) -> str:
    """DM sent when a shift a volunteer is on moves in time.

    Both windows are shown, because "the shift moved" without the old time is
    unverifiable against what they remember agreeing to.
    """
    details = _volunteer_shift_lines(position_name, label, starts_display, ends_display)
    blocks = ["A shift you're on has moved."]
    if old_starts_display or old_ends_display:
        was = " → ".join(p for p in (old_starts_display, old_ends_display) if p)
        blocks.append(f"**Was:** {was}")
    if details:
        blocks.append("\n".join(details))
    blocks.append("Tap **Acknowledge** to confirm you can still cover it.")
    return "\n\n".join(blocks)


def volunteer_released_dm(
    volunteer_name: str,
    position_name: str,
    label: Optional[str],
    starts_display: str,
    ends_display: str,
    hours_notice: Optional[float] = None,
    reason: Optional[str] = None,
) -> str:
    """DM to the coordinators when a volunteer gives a shift back."""
    details = _volunteer_shift_lines(position_name, label, starts_display, ends_display)
    blocks = [f"**{volunteer_name}** has given back a volunteer shift."]
    if details:
        blocks.append("\n".join(details))
    if hours_notice is not None:
        hours = round(hours_notice)
        blocks.append(f"Notice: about {hours} hour{'' if hours == 1 else 's'}.")
    if reason:
        blocks.append(f'Their reason: "{reason}"')
    blocks.append("This slot is open again.")
    return "\n\n".join(blocks)


def volunteer_ack_confirmation(position_name: str) -> str:
    return f"Thanks! Your **{position_name}** shift is acknowledged."
