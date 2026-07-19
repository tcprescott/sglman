"""Admin Challonge integration page (STAFF).

Manages the shared SGL Challonge service-account connection and lists the
tournaments linked to a Challonge bracket with a per-tournament Sync action.
"""

from nicegui import app, ui

from application.services import AuthService, ChallongeService, get_user_from_discord_id
from application.tenant_context import require_tenant_id
from application.utils.timezone import format_eastern_display
from models import Tournament
from theme.notify import notify_error


async def admin_challonge_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    is_staff = await AuthService.is_staff(actor)
    service = ChallongeService()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Challonge Integration').classes('page-title')
        ui.separator().classes('separator-spacing')

        @ui.refreshable
        async def connection_card() -> None:
            status = await service.get_connection_status()
            with ui.card().classes('w-full'):
                if not status.get('configured'):
                    ui.label('Challonge is not configured.').classes('text-error')
                    ui.label(
                        'The Challonge integration hasn’t been set up for this '
                        'deployment yet. Contact your platform administrator to '
                        'enable it.'
                    ).classes('text-muted')
                    return

                if status.get('connected'):
                    with ui.row().classes('items-center'):
                        ui.icon('link', color='positive')
                        ui.label(f"Connected as {status.get('challonge_username') or 'unknown'}").classes('text-bold')
                    if status.get('scopes'):
                        ui.label(f"Scopes: {status['scopes']}").classes('text-caption text-muted')
                    if status.get('token_expires_at'):
                        ui.label(
                            f"Token expires: {format_eastern_display(status['token_expires_at'])}"
                        ).classes('text-caption text-muted')
                    quota = status.get('request_quota')
                    used = status.get('request_usage', 0)
                    if quota:
                        warn = used >= quota * 0.8
                        ui.label(
                            f"API requests this month: {used} / {quota}"
                        ).classes('text-caption ' + ('text-error' if warn else 'text-muted'))
                    if is_staff:
                        ui.button('Disconnect', icon='link_off', on_click=disconnect).props('flat color=negative')
                else:
                    ui.label('The SGL Challonge account is not connected.').classes('text-muted')
                    if is_staff:
                        ui.button(
                            'Connect Challonge', icon='link',
                            on_click=lambda: ui.navigate.to('/challonge/connect'),
                        ).props('color=primary')

        async def disconnect() -> None:
            try:
                await service.disconnect(actor)
                ui.notify('Challonge disconnected.', color='positive')
            except (ValueError, PermissionError) as e:
                notify_error(e)
            await connection_card.refresh()

        await connection_card()

        ui.label('Linked tournaments').classes('section-title q-mt-md')

        @ui.refreshable
        async def linked_tournaments() -> None:
            tournaments = await Tournament.filter(challonge_tournament_id__isnull=False, tenant_id=require_tenant_id()).order_by('name')
            if not tournaments:
                ui.label('No tournaments are linked to Challonge yet. Link one from its edit dialog '
                         'on the Tournaments tab.').classes('text-muted')
                return
            for t in tournaments:
                with ui.row().classes('items-center w-full'):
                    ui.label(t.name).classes('text-bold')
                    if t.challonge_tournament_url:
                        ui.link('bracket', t.challonge_tournament_url, new_tab=True).classes('text-caption')
                    synced = (
                        format_eastern_display(t.challonge_last_synced_at)
                        if t.challonge_last_synced_at else 'never'
                    )
                    ui.label(f'Last synced: {synced}').classes('text-caption text-muted')
                    ui.space()
                    ui.button(
                        'Sync', icon='sync',
                        # Return the coroutine so NiceGUI awaits it in the button's
                        # slot; a bare background task has no slot, so the notify /
                        # refresh calls in sync_one would raise and be lost.
                        on_click=lambda _=None, tid=t.id: sync_one(tid),
                    ).props('flat color=primary')

        async def sync_one(tournament_id: int) -> None:
            try:
                result = await service.sync_bracket(tournament_id, actor, force=True)
                ui.notify(
                    f"Synced {result['participants']} participants, {result['matches']} matches.",
                    color='positive',
                )
            except ValueError as e:
                ui.notify(str(e), color='warning')
            except Exception as e:  # noqa: BLE001
                ui.notify(f'Sync failed: {e}', color='negative')
            await linked_tournaments.refresh()
            await connection_card.refresh()

        await linked_tournaments()
