"""Volunteer Section Page (self-service for volunteers)."""

from fastapi import Request
from nicegui import app, ui
from middleware.auth import protected_tab_page

from application.services import AuthService, TenantService, get_user_from_discord_id
from models import FeatureFlag, Role
from pages.admin_tabs.admin_schedule import admin_schedule_page
from pages.volunteer_tabs.availability import availability_tab
from pages.volunteer_tabs.my_shifts import my_shifts_tab
from theme.base import BaseLayout


def create() -> None:
    @protected_tab_page('/volunteer', roles=[Role.VOLUNTEER, Role.PROCTOR, Role.STAFF],
                        feature=FeatureFlag.VOLUNTEERS)
    async def volunteer_page(section: str = None, request: Request = None) -> None:
        ui.page_title(f'{await TenantService.current_community_name() or "Wizzrobe"} — Volunteer')
        discord_id = app.storage.user.get('discord_id', None)
        user = await get_user_from_discord_id(discord_id)

        roles = await AuthService.get_roles(user)
        is_staff = Role.STAFF in roles
        is_proctor = Role.PROCTOR in roles
        is_volunteer = Role.VOLUNTEER in roles

        tabs = []
        if is_volunteer:
            tabs.append({'label': 'My Availability', 'icon': 'event_available', 'content': availability_tab})
            tabs.append({'label': 'My Shifts', 'icon': 'assignment_ind', 'content': my_shifts_tab})
        if is_proctor or is_staff:
            tabs.append({'label': 'Proctor Station', 'icon': 'schedule',
                         'content': (admin_schedule_page, (), {'can_crud': is_staff})})
        show_admin = await AuthService.can_view_admin(user)
        base_path = f"{request.scope.get('root_path', '')}/volunteer" if request else '/volunteer'
        await BaseLayout(
            tabs=tabs, section=section, base_path=base_path, page_name='volunteer', user=user,
            show_admin=show_admin, show_volunteer=True,
        ).render()
