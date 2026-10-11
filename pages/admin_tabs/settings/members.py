"""Settings → Members: who can join this community, and what outsiders see."""

from nicegui import ui

from application.services import SystemConfigService, TenantService, TimezoneService
from application.services.system_config_service import (
    KEY_DISCORD_AUTO_JOIN,
    KEY_JOIN_PREVIEW,
    KEY_JOIN_REQUESTS,
)
from application.tenant_context import require_tenant_id
from application.utils.app_links import USERS, admin_url
from application.utils.timezone import timezone_label
from pages.admin_tabs.settings._common import current_actor
from theme.notify import notify_error
from theme.save_footer import SaveFooter
from theme.section import section_panel


async def _joining_card(can_edit: bool) -> None:
    join_preview = await SystemConfigService.get_bool(KEY_JOIN_PREVIEW)
    discord_auto_join = await SystemConfigService.get_bool(KEY_DISCORD_AUTO_JOIN)
    join_requests = await SystemConfigService.get_bool(KEY_JOIN_REQUESTS, default=True)
    discord_invite_url = await SystemConfigService.get_discord_invite_url() or ''
    tenant = await TenantService.get_by_id(require_tenant_id())
    guild_linked = bool(tenant and tenant.discord_guild_id)
    tenant_tz_label = timezone_label(await TimezoneService.tenant_timezone_name())

    card = await section_panel(
        'Joining this community', icon='meeting_room',
        subtitle='Who becomes a member, and what the join page shows everyone else.',
    )
    with card.body.classes('gap-4'):
        join_preview_input = ui.switch(
            'Show today’s matches to non-members', value=join_preview,
        )
        ui.label(
            'People who are not members of this community see a join page. '
            'With this on, that page also lists today’s match times and '
            f'player names, on the community’s clock ({tenant_tz_label}). '
            'Published brackets are always listed there — they are public '
            'pages already. Off by default.'
        ).classes('text-caption text-grey')

        join_requests_input = ui.switch(
            'Take join requests', value=join_requests,
        )
        ui.label(
            'Non-members can ask to join from the join page, and Staff approve '
            'or deny on the Users tab. Turn this off to stop new requests; '
            'ones already waiting stay there for you to decide. Discord '
            'auto-join below keeps working either way. On by default.'
        ).classes('text-caption text-grey')
        ui.button(
            'Open the join queue', icon='manage_accounts',
            on_click=lambda: ui.navigate.to(admin_url(USERS)),
        ).props('flat dense no-caps color=primary').classes('self-start')

        discord_auto_join_input = ui.switch(
            'Let Discord server members in without asking', value=discord_auto_join,
        )
        ui.label(
            'Anyone in this community’s linked Discord server becomes a member '
            'the first time they open it, instead of filing a join request. '
            'They get no roles from this; role mappings still decide those. '
            'Leaving the server later doesn’t remove them. Off by default.'
            if guild_linked else
            'No Discord server is linked to this community, so this does '
            'nothing until one is.'
        ).classes('text-caption text-grey')

        discord_invite_input = ui.input(
            'Discord invite link', value=discord_invite_url,
            placeholder='https://discord.gg/abc123',
        ).classes('w-full')
        ui.label(
            'Shown on the join page as a Join the Discord server button, and on '
            'the message a declined requester gets. Use an invite that doesn’t '
            'expire. Leave blank to hide the button.'
        ).classes('text-caption text-grey')

    async def save_join() -> bool:
        try:
            actor = await current_actor()
            invite_raw = SystemConfigService.normalize_discord_invite_url(
                discord_invite_input.value,
            )
            await SystemConfigService.set_raw(
                KEY_JOIN_PREVIEW, 'true' if join_preview_input.value else 'false', actor,
            )
            await SystemConfigService.set_raw(
                KEY_JOIN_REQUESTS,
                'true' if join_requests_input.value else 'false', actor,
            )
            await SystemConfigService.set_raw(
                KEY_DISCORD_AUTO_JOIN,
                'true' if discord_auto_join_input.value else 'false', actor,
            )
            await SystemConfigService.set_discord_invite_url(invite_raw, actor)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return False
        discord_invite_input.value = invite_raw
        ui.notify('Join settings saved', color='positive')
        return True

    controls = (join_preview_input, join_requests_input, discord_auto_join_input, discord_invite_input)
    with card.panel:
        SaveFooter(save_join, enabled=can_edit).watch(*controls)
    if not can_edit:
        for control in controls:
            control.disable()


async def members_settings_pane(can_edit: bool) -> None:
    await _joining_card(can_edit)
