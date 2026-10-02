"""The opponent's side of a reschedule request: read it, and agree if it works.

The opponent DM says "Press **Agree** if that works for you", and until this
existed the only Agree was a Discord button, so a player reading the web-push
copy of that DM, or anyone who prefers the site, had no way to do what it asked.
The dialog is what the DM's link button opens; :func:`render_agreement_summary`
is shared with the card on My Schedule so the two describe a request the same
way.

Agreement is advice to staff, not a decision, and every line here says so: a
button that reads like a veto and turns out to be a hint is worse than none.
"""

from typing import Awaitable, Callable, Optional

from nicegui import ui

from application.services import MatchRescheduleService
from application.utils.timezone import format_local_display
from models import MatchRescheduleRequest, RescheduleRequestKind, User
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.notify import notify_error

AGREE_NOTE = "Agreeing tells staff the change works for you. Staff still make the call."


def agreement_headline(request: MatchRescheduleRequest) -> str:
    """'PJ Bob asked staff to move your match' — who, and what they want."""
    verb = 'call off' if request.kind is RescheduleRequestKind.CANCEL else 'move'
    return f'{request.requested_by.preferred_name} asked staff to {verb} your match'


def agreement_detail_lines(request: MatchRescheduleRequest) -> list[str]:
    """The tournament, the time now, what they proposed, and why."""
    current = request.original_scheduled_at or request.match.scheduled_at
    lines = [request.match.tournament.name]
    if current is not None:
        lines.append(f'Now: {format_local_display(current)}')
    if request.kind is RescheduleRequestKind.CANCEL:
        lines.append('Asking to: call the match off')
    elif request.proposed_at is not None:
        lines.append(f'Proposed: {format_local_display(request.proposed_at)}')
    else:
        lines.append("Proposed: no specific time, they just can't make this one")
    if request.reason:
        lines.append(f'Their reason: {request.reason}')
    return lines


def render_agreement_summary(request: MatchRescheduleRequest) -> None:
    ui.label(agreement_headline(request)).classes('text-bold')
    for line in agreement_detail_lines(request):
        ui.label(line).classes('text-caption text-grey-7')


async def agree(
    request: MatchRescheduleRequest, actor: User,
) -> bool:
    """Record agreement and say so. ``False`` (with a toast) when refused."""
    try:
        await MatchRescheduleService().record_opponent_agreement(request.id, actor)
    except (ValueError, PermissionError) as e:
        notify_error(e)
        return False
    ui.notify(
        f"Done. Staff will see you're happy with "
        f"{request.requested_by.preferred_name}'s request.",
        color='positive',
    )
    return True


class RescheduleAgreeDialog:
    """One request, opened from the opponent DM's link button."""

    def __init__(
        self,
        request: MatchRescheduleRequest,
        actor: User,
        *,
        on_agreed: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        self.request = request
        self.actor = actor
        self.on_agreed = on_agreed

    async def open(self) -> None:
        with form_dialog('Your opponent asked to reschedule') as dialog:
            with ui.column().classes('q-pa-md gap-2 full-width'):
                render_agreement_summary(self.request)
                ui.label(AGREE_NOTE).classes('text-caption q-mt-sm')

                async def do_agree() -> None:
                    if not await agree(self.request, self.actor):
                        return
                    dialog.close()
                    if self.on_agreed is not None:
                        await self.on_agreed()

                with dialog_actions().classes('justify-end'):
                    ui.button('Not now', on_click=dialog.close).props('flat')
                    ui.button('Agree', icon='thumb_up', on_click=do_agree) \
                        .props('color=positive')
        dialog.open()
