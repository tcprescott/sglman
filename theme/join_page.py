"""The door beside the membership gate.

A non-member reaching a tenant page gets this rather than a 403. The distinction
matters: forbidden-by-role is a dead end, but not-a-member is a state with a
remedy, and the page whose whole job is to offer that remedy should not open by
telling you no.

Rendered synchronously into the current page context, like
:mod:`theme.error_page`, so it can be called from the middleware decorator
without restructuring it.
"""

from typing import Optional

from nicegui import background_tasks, context, ui

from models import JoinRequestStatus, User
from theme.base import BaseLayout


def render_join_page(
    *,
    tenant_id: int,
    tenant_name: str,
    user: Optional[User],
    pending: bool = False,
) -> None:
    """Ask to join, or say the request is already in.

    ``pending`` is resolved by the caller (which has already loaded the user), so
    this stays synchronous.
    """
    ui.page_title(f'{tenant_name} — Join')

    try:
        BaseLayout(user=user).render_chrome()
    except Exception:  # pragma: no cover - defensive, mirroring error_page
        pass

    with ui.column().classes('error-page-container'):
        with ui.card().classes('error-card join-card'):
            ui.icon('meeting_room').props('size=xl color=primary')
            ui.label(tenant_name).classes('error-headline')

            if user is None:
                ui.label(
                    'Sign in to ask to join this community.'
                ).classes('error-message')
                ui.button('Sign in', icon='login',
                          on_click=lambda: ui.navigate.to('login')).props('color=primary')
                return

            if pending:
                # Once asked, there is nothing else to offer — a second button
                # would only produce a second identical request.
                ui.label(
                    'Your request to join is with this community’s staff. '
                    'You will get a message either way.'
                ).classes('error-message')
                return

            ui.label(
                'You are not a member of this community yet. Ask to join and its '
                'staff will decide.'
            ).classes('error-message')

            message = ui.textarea(
                'Anything they should know? (optional)',
            ).classes('w-full').props('maxlength=500 counter autogrow')

            async def submit(client) -> None:
                from application.services import TenantMembershipService

                with client:
                    try:
                        await TenantMembershipService().request_to_join(
                            user, tenant_id, message.value,
                        )
                    except (ValueError, PermissionError) as e:
                        ui.notify(str(e), color='warning')
                        return
                    ui.notify('Request sent.', color='positive')
                    # Re-enter the page so it re-renders in its pending state
                    # rather than leaving a button that would resubmit.
                    ui.navigate.reload()

            ui.button(
                'Request access', icon='how_to_reg',
                on_click=lambda: background_tasks.create(submit(context.client)),
            ).props('color=primary')


async def resolve_join_state(user: Optional[User], tenant_id: int) -> bool:
    """Whether this user already has a pending request in this tenant."""
    if user is None:
        return False
    from application.services import TenantMembershipService

    request = await TenantMembershipService().get_request(user, tenant_id)
    return request is not None and request.status is JoinRequestStatus.PENDING
