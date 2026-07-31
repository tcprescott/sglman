"""Volunteer Section Page (self-service for volunteers)."""

from fastapi import Request
from nicegui import app, ui

from application.services import AuthService, TenantService, get_user_from_discord_id
from middleware.auth import protected_tab_page
from models import FeatureFlag, Role
from pages.volunteer_tabs.availability import availability_tab
from pages.volunteer_tabs.my_shifts import my_shifts_tab
from pages.volunteer_tabs.proctor_station import proctor_station_tab
from theme.base import BaseLayout


def create() -> None:
    @protected_tab_page('/volunteer', roles=[Role.VOLUNTEER, Role.PROCTOR, Role.STAFF],
                        feature=FeatureFlag.VOLUNTEERS)
    async def volunteer_page(section: str | None = None, request: Request = None) -> None:
        ui.page_title(f'{await TenantService.current_community_name() or "Wizzrobe"} — Volunteer')
        discord_id = app.storage.user.get('discord_id', None)
        user = await get_user_from_discord_id(discord_id)

        roles = await AuthService.get_roles(user)
        # Staff-equivalence throughout, so a platform super-admin sees the whole
        # hub in a tenant they hold no roles in.
        is_staff = await AuthService.is_staff(user)
        is_proctor = Role.PROCTOR in roles
        is_volunteer = Role.VOLUNTEER in roles

        tabs = []
        # The two self-service tabs read the *signed-in* user's own availability
        # and shifts, so they are safe (and empty) for someone who volunteers for
        # nothing; saving availability still requires a volunteer opt-in, which
        # the service enforces. Home already offers My Availability to everyone.
        if is_volunteer or is_staff:
            tabs.append({'label': 'My Availability', 'icon': 'event_available', 'content': availability_tab})
            tabs.append({'label': 'My Shifts', 'icon': 'assignment_ind', 'content': my_shifts_tab})
        if is_proctor or is_staff:
            tabs.append({'label': 'Proctor Station', 'icon': 'sports_esports',
                         'content': proctor_station_tab})
        show_admin = await AuthService.can_view_admin(user)
        base_path = f"{request.scope.get('root_path', '')}/volunteer" if request else '/volunteer'
        await BaseLayout(
            tabs=tabs, section=section, base_path=base_path, page_name='volunteer', user=user,
            show_admin=show_admin, show_volunteer=True,
        ).render()
