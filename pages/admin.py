"""Admin Dashboard Page"""

from dataclasses import dataclass

from fastapi import Request
from nicegui import app, ui

from application.services import (
    AuthService,
    FeatureFlagService,
    SetupStep,
    TenantService,
    TenantSetupService,
    get_user_from_discord_id,
)
from application.tenant_context import get_current_tenant_id
from middleware.auth import protected_tab_page
from models import FeatureFlag, Role
from pages.admin_tabs.admin_brackets import admin_brackets_page
from pages.admin_tabs.admin_challonge import admin_challonge_page
from pages.admin_tabs.admin_discord_events import admin_discord_events_page
from pages.admin_tabs.admin_discord_roles import admin_discord_roles_page
from pages.admin_tabs.admin_equipment import admin_equipment_page
from pages.admin_tabs.admin_features import admin_features_page
from pages.admin_tabs.admin_feedback import admin_feedback_page
from pages.admin_tabs.admin_presets import admin_presets_page
from pages.admin_tabs.admin_qualifiers import admin_qualifiers_page
from pages.admin_tabs.admin_racetime import admin_racetime_page
from pages.admin_tabs.admin_randomizer_keys import admin_randomizer_keys_page
from pages.admin_tabs.admin_schedule import admin_schedule_page
from pages.admin_tabs.admin_service_health import admin_service_health_page
from pages.admin_tabs.admin_settings import admin_stream_rooms_page, admin_tournaments_page
from pages.admin_tabs.admin_setup import admin_setup_page
from pages.admin_tabs.admin_speedgaming import admin_speedgaming_page
from pages.admin_tabs.admin_system_config import admin_system_config_page
from pages.admin_tabs.admin_theme import admin_theme_page
from pages.admin_tabs.admin_timezone import admin_timezone_page
from pages.admin_tabs.admin_users import admin_users_page
from pages.admin_tabs.admin_volunteer_roster import admin_volunteer_roster_page
from pages.admin_tabs.admin_volunteers import admin_volunteers_page
from pages.admin_tabs.admin_webhooks import admin_webhooks_page
from pages.admin_tabs.reports import reports_page
from pages.admin_tabs.triforce_texts import admin_triforce_texts_page
from theme.base import BaseLayout
from theme.tables.match_access import MatchBoardAccess

_ADMIN_GROUP_ORDER = ['Operations', 'Online play', 'Community', 'Integrations', 'System']


@dataclass(frozen=True)
class AdminAccess:
    """What the viewer may reach in this tenant, resolved once per page load."""

    is_staff: bool = False
    is_stream_manager: bool = False
    is_volunteer_coordinator: bool = False
    is_equipment_manager: bool = False
    is_preset_manager: bool = False
    is_sync_admin: bool = False
    is_qualifier_admin: bool = False
    is_tournament_admin: bool = False
    is_crew_coordinator: bool = False
    is_qualifier_owner: bool = False
    # The tournaments this viewer administers or coordinates, for the surfaces
    # that scope to them. Excluded from ``any()``: it is derived from the two
    # booleans above, and a set is not an access grant of its own.
    operated_tournament_ids: frozenset[int] = frozenset()

    def any(self) -> bool:
        return any(getattr(self, f) for f in self.__dataclass_fields__
                   if f != 'operated_tournament_ids')


def build_admin_tabs(
    access: AdminAccess,
    live: set,
    reports_kwargs: dict,
    setup_steps: list[SetupStep] | None = None,
    base_path: str = '/admin',
    *,
    match_id: int | None = None,
    day: str | None = None,
) -> list[dict]:
    """The admin drawer's tabs, ordered by group.

    Module-level and pure so the ordering rules — notably which tab a new
    community lands on — are testable without a browser.
    """
    is_staff = access.is_staff
    is_ta_any = access.is_tournament_admin
    is_cc_any = access.is_crew_coordinator
    is_qa_any = access.is_qualifier_owner
    is_sm = access.is_stream_manager
    # What the board may offer, resolved per capability rather than from one
    # can-do-everything boolean — the services have always been this granular.
    board_access = MatchBoardAccess.for_roles(
        is_staff=is_staff,
        is_tournament_admin=is_ta_any,
        is_stream_manager=is_sm,
        is_crew_coordinator=is_cc_any,
    )
    # Staff and the stream manager operate community-wide; a TA/CC's authority is
    # per tournament, so their board is narrowed to the ones they run rather than
    # showing every match in the community with controls that refuse.
    board_tournament_ids = (
        None if (is_staff or is_sm)
        else sorted(access.operated_tournament_ids)
    )
    # Each tab that can be deep-linked gets its own params. `state` in
    # reports_kwargs is the Reports tab's own filter and deliberately not
    # reused for the board's state filter — one param must not mean two things.
    schedule_kwargs = {
        'access': board_access,
        'match_id': match_id,
        'tournament_ids': board_tournament_ids,
    }

    tabs = []
    # Each tab carries a drawer 'group'; the list is stable-sorted by
    # _ADMIN_GROUP_ORDER below so the drawer reads as labeled sections
    # instead of a flat scroll. Icons are unique per destination (no repeats).
    #
    # Setup comes first while the community is not ready: BaseLayout defaults to
    # tabs[0], so a new community lands on the checklist rather than on Create
    # Match, which cannot yet succeed. It disappears on its own once the
    # required steps are done — nothing stores that it was seen.
    if setup_steps and not TenantSetupService.is_ready(setup_steps) and (is_staff or is_ta_any):
        tabs.append({'label': 'Setup', 'icon': 'checklist', 'group': 'Operations',
                     'content': (admin_setup_page, (), {'steps': setup_steps, 'base_path': base_path})})
    # STREAM_MANAGER is here because assigning a stage is a match-board action
    # and this is the only board that offers it — the role existed for that job
    # with no surface that did it. What they get once here is one control:
    # ``board_access`` grants them ``assign_stream`` and nothing else.
    if is_staff or is_ta_any or is_cc_any or is_sm:
        tabs.append({'label': 'Schedule', 'icon': 'schedule', 'group': 'Operations', 'content': (admin_schedule_page, (), schedule_kwargs)})
    if is_staff:
        tabs.append({'label': 'Users', 'icon': 'manage_accounts', 'group': 'Operations', 'content': admin_users_page})
    if is_staff or is_ta_any:
        tabs.append({'label': 'Tournaments', 'icon': 'emoji_events', 'group': 'Operations', 'content': admin_tournaments_page})
    if is_staff or access.is_stream_manager:
        tabs.append({'label': 'Stream Rooms', 'icon': 'tv', 'group': 'Operations', 'content': admin_stream_rooms_page})
    if is_staff or access.is_preset_manager:
        tabs.append({'label': 'Presets', 'icon': 'tune', 'group': 'Online play', 'content': admin_presets_page})
        tabs.append({'label': 'Randomizer Keys', 'icon': 'key', 'group': 'Online play', 'content': admin_randomizer_keys_page})
    if (is_staff or access.is_qualifier_admin or is_qa_any) and FeatureFlag.ASYNC_QUALIFIERS in live:
        tabs.append({'label': 'Qualifiers', 'icon': 'timer', 'group': 'Online play', 'content': admin_qualifiers_page})
    if (is_staff or access.is_sync_admin) and FeatureFlag.RACETIME_ROOMS in live:
        tabs.append({'label': 'Racetime', 'icon': 'sports_esports', 'group': 'Online play', 'content': admin_racetime_page})
    if (is_staff or access.is_sync_admin) and FeatureFlag.SPEEDGAMING_ETL in live:
        tabs.append({'label': 'SpeedGaming', 'icon': 'sync_alt', 'group': 'Online play', 'content': admin_speedgaming_page})
    if is_staff and FeatureFlag.CHALLONGE in live:
        tabs.append({'label': 'Challonge', 'icon': 'account_tree', 'group': 'Online play', 'content': admin_challonge_page})
    if is_staff and FeatureFlag.BRACKETS in live:
        tabs.append({'label': 'Brackets', 'icon': 'schema', 'group': 'Online play', 'content': admin_brackets_page})
    if (is_staff or is_ta_any) and FeatureFlag.TRIFORCE_TEXTS in live:
        tabs.append({'label': 'Triforce Texts', 'icon': 'svguse:/static/triforce.svg#triforce|0 0 512 512', 'group': 'Community', 'content': admin_triforce_texts_page})
    if (is_staff or access.is_volunteer_coordinator) and FeatureFlag.VOLUNTEERS in live:
        tabs.append({'label': 'Vol. Roster', 'icon': 'groups', 'group': 'Community', 'content': admin_volunteer_roster_page})
        tabs.append({'label': 'Vol. Schedule', 'icon': 'event_available', 'group': 'Community', 'content': (admin_volunteers_page, (), {'day': day})})
    if (is_staff or access.is_equipment_manager) and FeatureFlag.EQUIPMENT in live:
        tabs.append({'label': 'Equipment', 'icon': 'inventory_2', 'group': 'Community', 'content': admin_equipment_page})
    if is_staff:
        tabs.append({'label': 'Feedback', 'icon': 'feedback', 'group': 'Community', 'content': admin_feedback_page})
    if is_staff or access.is_sync_admin:
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
        tabs.append({'label': 'Timezone', 'icon': 'schedule', 'group': 'System', 'content': admin_timezone_page})

    tabs.sort(key=lambda t: _ADMIN_GROUP_ORDER.index(t['group']))
    return tabs


def create() -> None:
    @protected_tab_page('/admin')
    async def admin_dashboard_page(
        section: str | None = None,
        request: Request = None,
        report: str | None = None,
        start: str | None = None,
        end: str | None = None,
        bucket: str | None = None,
        tournament_id: int | None = None,
        user_id: int | None = None,
        stream_room_id: int | None = None,
        state: str | None = None,
        approval: str | None = None,
        action: str | None = None,
        focus: str | None = None,
        category: str | None = None,
        page: int | None = None,
        match_id: int | None = None,
        day: str | None = None,
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
        # Tenant-filtered inside the service: these reverse relations hang off
        # the *global* User, so unfiltered they let a tournament admin in one
        # community through this gate in every other one. The ids (not just
        # "any?") because the Schedule board scopes to them.
        admin_tournament_ids, cc_tournament_ids = await AuthService.tournament_scope(user)
        access = AdminAccess(
            # Staff-equivalence (not the literal grant) so a platform super-admin
            # has full authority in this tenant.
            is_staff=await AuthService.is_staff(user),
            is_stream_manager=Role.STREAM_MANAGER in roles,
            is_volunteer_coordinator=Role.VOLUNTEER_COORDINATOR in roles,
            is_equipment_manager=Role.EQUIPMENT_MANAGER in roles,
            is_preset_manager=Role.PRESET_MANAGER in roles,
            is_sync_admin=Role.SYNC_ADMIN in roles,
            is_qualifier_admin=Role.QUALIFIER_ADMIN in roles,
            is_tournament_admin=bool(admin_tournament_ids),
            is_crew_coordinator=bool(cc_tournament_ids),
            is_qualifier_owner=await user.admin_async_qualifiers.filter(
                tenant_id=get_current_tenant_id()).exists(),
            operated_tournament_ids=frozenset(admin_tournament_ids | cc_tournament_ids),
        )

        # Per-tenant feature flags: a subsystem's tab only appears when the
        # tenant has that feature live (available AND enabled), in addition to
        # the role gate. Loaded once for all tabs, as is the setup checklist.
        live = await FeatureFlagService().enabled_flags()
        setup_steps = await TenantSetupService().status()

        if not access.any():
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

        base_path = f"{request.scope.get('root_path', '')}/admin" if request else '/admin'
        tabs = build_admin_tabs(
            access, live, reports_kwargs, setup_steps, base_path,
            match_id=match_id, day=day,
        )

        base_layout = BaseLayout(
            tabs=tabs, section=section, base_path=base_path, page_name='admin', user=user,
            show_admin=True,
        )
        await base_layout.render()
