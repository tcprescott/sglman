"""Admin Dashboard Page"""

from fastapi import Request
from nicegui import app, ui
from middleware.auth import protected_tab_page

from application.services import AuthService, FeatureFlagService, TenantService, get_user_from_discord_id
from models import FeatureFlag, Role
from pages.admin_tabs.admin_schedule import admin_schedule_page
from pages.admin_tabs.admin_settings import admin_stream_rooms_page, admin_tournaments_page
from pages.admin_tabs.admin_users import admin_users_page
from pages.admin_tabs.admin_volunteer_roster import admin_volunteer_roster_page
from pages.admin_tabs.admin_volunteers import admin_volunteers_page
from pages.admin_tabs.reports import reports_page
from pages.admin_tabs.triforce_texts import admin_triforce_texts_page
from pages.admin_tabs.admin_system_config import admin_system_config_page
from pages.admin_tabs.admin_theme import admin_theme_page
from pages.admin_tabs.admin_challonge import admin_challonge_page
from pages.admin_tabs.admin_discord_roles import admin_discord_roles_page
from pages.admin_tabs.admin_webhooks import admin_webhooks_page
from pages.admin_tabs.admin_equipment import admin_equipment_page
from pages.admin_tabs.admin_feedback import admin_feedback_page
from pages.admin_tabs.admin_presets import admin_presets_page
from pages.admin_tabs.admin_qualifiers import admin_qualifiers_page
from pages.admin_tabs.admin_racetime import admin_racetime_page
from pages.admin_tabs.admin_speedgaming import admin_speedgaming_page
from pages.admin_tabs.admin_discord_events import admin_discord_events_page
from pages.admin_tabs.admin_service_health import admin_service_health_page
from pages.admin_tabs.admin_features import admin_features_page
from theme.base import BaseLayout


def create() -> None:
    @protected_tab_page('/admin')
    async def admin_dashboard_page(
        section: str = None,
        request: Request = None,
        report: str = None,
        start: str = None,
        end: str = None,
        bucket: str = None,
        tournament_id: int = None,
        user_id: int = None,
        stream_room_id: int = None,
        state: str = None,
        approval: str = None,
        action: str = None,
        focus: str = None,
        category: str = None,
        page: int = None,
    ) -> None:
        ui.page_title(f'{await TenantService.current_community_name() or "Wizzrobe"} — Admin')
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            with ui.row():
                ui.label('You must be logged in to view this page.').classes('text-error')
            return

        # get_user_from_discord_id enforces is_active, so a deactivated account
        # loses admin access on its next request — consistent with the REST API
        # and the login flow, and not bypassed by this non-role-gated page.
        user = await get_user_from_discord_id(discord_id)
        if user is None:
            with ui.row():
                ui.label('User not found in the database.').classes('text-error')
            return

        roles = await AuthService.get_roles(user)
        is_staff = Role.STAFF in roles
        is_stream_manager = Role.STREAM_MANAGER in roles
        is_volunteer_coordinator = Role.VOLUNTEER_COORDINATOR in roles
        is_equipment_manager = Role.EQUIPMENT_MANAGER in roles
        is_preset_manager = Role.PRESET_MANAGER in roles
        is_sync_admin = Role.SYNC_ADMIN in roles
        is_qualifier_admin = Role.QUALIFIER_ADMIN in roles
        is_ta_any = await user.admin_tournaments.all().exists()
        is_cc_any = await user.crew_coordinated_tournaments.all().exists()
        is_qa_any = await user.admin_async_qualifiers.all().exists()

        # Per-tenant feature flags: a subsystem's tab only appears when the
        # tenant has that feature live (available AND enabled), in addition to
        # the role gate. Loaded once for all tabs.
        live = await FeatureFlagService().enabled_flags()

        if not (is_staff or is_stream_manager or is_equipment_manager
                or is_volunteer_coordinator or is_preset_manager or is_sync_admin
                or is_qualifier_admin or is_qa_any or is_ta_any or is_cc_any):
            from theme.error_page import render_error_page
            render_error_page(
                status_code=403, headline='Forbidden',
                message="You don't have permission to view the admin area.",
                user=user,
            )
            return

        reports_kwargs = {
            'report': report,
            'start': start,
            'end': end,
            'bucket': bucket,
            'tournament_id': tournament_id,
            'user_id': user_id,
            'stream_room_id': stream_room_id,
            'state': state,
            'approval': approval,
            'action': action,
            'focus': focus,
            'category': category,
            'page': page,
        }

        can_crud = is_staff or is_ta_any
        tabs = []
        # Each tab carries a drawer 'group'; the list is stable-sorted by
        # _ADMIN_GROUP_ORDER below so the 21-item drawer reads as labeled sections
        # instead of a flat scroll. Icons are unique per destination (no repeats).
        if is_staff or is_ta_any or is_cc_any:
            tabs.append({'label': 'Schedule', 'icon': 'schedule', 'group': 'Operations', 'content': (admin_schedule_page, (), {'can_crud': can_crud})})
        if is_staff:
            tabs.append({'label': 'Users', 'icon': 'manage_accounts', 'group': 'Operations', 'content': admin_users_page})
        if is_staff or is_ta_any:
            tabs.append({'label': 'Tournaments', 'icon': 'emoji_events', 'group': 'Operations', 'content': admin_tournaments_page})
        if is_staff or is_stream_manager:
            tabs.append({'label': 'Stream Rooms', 'icon': 'tv', 'group': 'Operations', 'content': admin_stream_rooms_page})
        if is_staff or is_preset_manager:
            tabs.append({'label': 'Presets', 'icon': 'tune', 'group': 'Online play', 'content': admin_presets_page})
        if (is_staff or is_qualifier_admin or is_qa_any) and FeatureFlag.ASYNC_QUALIFIERS in live:
            tabs.append({'label': 'Qualifiers', 'icon': 'timer', 'group': 'Online play', 'content': admin_qualifiers_page})
        if (is_staff or is_sync_admin) and FeatureFlag.RACETIME_ROOMS in live:
            tabs.append({'label': 'Racetime', 'icon': 'sports_esports', 'group': 'Online play', 'content': admin_racetime_page})
        if (is_staff or is_sync_admin) and FeatureFlag.SPEEDGAMING_ETL in live:
            tabs.append({'label': 'SpeedGaming', 'icon': 'sync_alt', 'group': 'Online play', 'content': admin_speedgaming_page})
        if is_staff and FeatureFlag.CHALLONGE in live:
            tabs.append({'label': 'Challonge', 'icon': 'account_tree', 'group': 'Online play', 'content': admin_challonge_page})
        if (is_staff or is_ta_any) and FeatureFlag.TRIFORCE_TEXTS in live:
            tabs.append({'label': 'Triforce Texts', 'icon': 'svguse:/static/triforce.svg#triforce|0 0 512 512', 'group': 'Community', 'content': admin_triforce_texts_page})
        if (is_staff or is_volunteer_coordinator) and FeatureFlag.VOLUNTEERS in live:
            tabs.append({'label': 'Vol. Roster', 'icon': 'groups', 'group': 'Community', 'content': admin_volunteer_roster_page})
            tabs.append({'label': 'Vol. Schedule', 'icon': 'event_available', 'group': 'Community', 'content': admin_volunteers_page})
        if (is_staff or is_equipment_manager) and FeatureFlag.EQUIPMENT in live:
            tabs.append({'label': 'Equipment', 'icon': 'inventory_2', 'group': 'Community', 'content': admin_equipment_page})
        if is_staff:
            tabs.append({'label': 'Feedback', 'icon': 'feedback', 'group': 'Community', 'content': admin_feedback_page})
        if is_staff or is_sync_admin:
            tabs.append({'label': 'Discord Events', 'icon': 'event', 'group': 'Integrations', 'content': admin_discord_events_page})
        if is_staff:
            tabs.append({'label': 'Discord Roles', 'icon': 'hub', 'group': 'Integrations', 'content': admin_discord_roles_page})
        if is_staff:
            tabs.append({'label': 'Webhooks', 'icon': 'webhook', 'group': 'Integrations', 'content': admin_webhooks_page})
        if is_staff or is_ta_any or is_cc_any:
            tabs.append({'label': 'Reports', 'icon': 'analytics', 'group': 'System', 'content': (reports_page, (), reports_kwargs)})
        if is_staff:
            tabs.append({'label': 'Service Health', 'icon': 'monitor_heart', 'group': 'System', 'content': admin_service_health_page})
        if is_staff:
            tabs.append({'label': 'Features', 'icon': 'toggle_on', 'group': 'System', 'content': admin_features_page})
        if is_staff:
            tabs.append({'label': 'Settings', 'icon': 'settings', 'group': 'System', 'content': admin_system_config_page})
        if is_staff:
            tabs.append({'label': 'Appearance', 'icon': 'palette', 'group': 'System', 'content': admin_theme_page})

        _ADMIN_GROUP_ORDER = ['Operations', 'Online play', 'Community', 'Integrations', 'System']
        tabs.sort(key=lambda t: _ADMIN_GROUP_ORDER.index(t['group']))

        base_path = f"{request.scope.get('root_path', '')}/admin" if request else '/admin'
        base_layout = BaseLayout(
            tabs=tabs, section=section, base_path=base_path, page_name='admin', user=user,
            show_admin=True, show_volunteer=user is not None,
        )
        await base_layout.render()
