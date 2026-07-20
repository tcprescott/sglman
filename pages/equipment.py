"""Equipment asset detail page — the QR-code target for each asset.

A scannable QR code on this page encodes the asset's own URL, so scanning it
jumps straight here (login required). Logged-in users see the asset summary,
its QR code, and loan history; those with the right roles can check the asset
out or back in, and managers can edit/delete it.
"""

from nicegui import app, ui
from middleware.auth import protected_page

from application.services import AuthService, EquipmentService, TenantService, get_user_from_discord_id
from application.tenant_context import get_current_tenant_id
from models import FeatureFlag
from application.utils.environment import get_base_url
from application.utils.qrcode_util import asset_qr_data_uri, asset_qr_png_bytes
from application.utils.tenant_urls import tenant_url
from application.utils.timezone import format_eastern_display
from theme.base import BaseLayout
from theme.dialog import EquipmentDialog, open_checkout, quick_checkin

_STATUS_LABELS = {
    'available': 'Available',
    'checked_out': 'Checked out',
    'retired': 'Retired',
}


def create() -> None:
    @protected_page('/equipment/{asset_id}', feature=FeatureFlag.EQUIPMENT)
    async def equipment_detail(asset_id: int) -> None:
        ui.page_title(f'{await TenantService.current_community_name() or "Wizzrobe"} — Equipment')
        # get_user_from_discord_id enforces is_active so a deactivated user
        # cannot keep reading asset owner labels / manager-only private notes.
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        show_admin = await AuthService.can_view_admin(user)
        await BaseLayout(
            user=user, show_admin=show_admin, show_volunteer=user is not None,
        ).render()

        if user is None:
            ui.label('You must be logged in to view this page.').classes('text-error')
            return

        service = EquipmentService()
        can_manage = await AuthService.can_manage_equipment(user)
        can_checkout = await AuthService.can_checkout_equipment(user)
        can_checkin = await AuthService.can_checkin_equipment(user)

        @ui.refreshable
        async def render_detail() -> None:
            asset = await service.get_asset(asset_id)
            if asset is None:
                ui.label('Asset not found.').classes('text-error')
                return

            open_loan = await service.current_loan(asset)
            history = await service.loan_history(asset)

            # Tenant-qualified deep link so a scanned QR resolves to this
            # community: its own custom domain when set, else the path-mode form
            # (/t/<slug>/equipment/<id>). On the bare platform host a bare
            # /equipment/<id> would 404 (protected pages require a tenant).
            tid = get_current_tenant_id()
            tenant = await TenantService.get_by_id(tid) if tid is not None else None
            asset_link = (
                tenant_url(tenant, f'/equipment/{asset.id}')
                if tenant is not None else f'{get_base_url()}/equipment/{asset.id}'
            )

            with ui.card().classes('page-container-narrow w-full q-pa-lg q-mt-md column'):
                with ui.row().classes('header-row items-center'):
                    ui.label(f'#{asset.asset_number} · {asset.name}').classes('page-title')
                    ui.badge(
                        _STATUS_LABELS.get(asset.status.value, asset.status.value),
                        color=('positive' if asset.status.value == 'available'
                               else 'warning' if asset.status.value == 'checked_out' else 'grey'),
                    )
                ui.separator().classes('separator-spacing')

                with ui.row().classes('w-full gap-6 items-start'):
                    with ui.column().classes('gap-1'):
                        if asset.description:
                            ui.label(asset.description)
                        community = await TenantService.current_community_name()
                        ui.label(f'Owner: {asset.owner_label(community)}').classes('italic-note')
                        if open_loan is not None:
                            ui.label(
                                f'Checked out to {open_loan.borrower.preferred_name} '
                                f'({format_eastern_display(open_loan.checked_out_at)})'
                            ).classes('italic-note')
                        if can_manage and asset.private_notes:
                            with ui.card().classes('q-pa-sm bg-amber-1 text-grey-10'):
                                ui.label('Private notes').classes('text-caption text-bold')
                                ui.label(asset.private_notes)

                    with ui.column().classes('items-center gap-1'):
                        ui.image(asset_qr_data_uri(asset_link)).classes('w-40 h-40')
                        ui.label(asset_link).classes('text-caption')

                        def download_qr():
                            ui.download(asset_qr_png_bytes(asset_link), f'asset-{asset.asset_number}-qr.png')

                        with ui.row().classes('gap-1'):
                            ui.button('Download QR', icon='download', on_click=download_qr).props('flat dense')
                            if can_manage:
                                ui.button(
                                    'Print label', icon='print',
                                    on_click=lambda aid=asset.id: ui.navigate.to(
                                        f'/equipment/qr-labels?ids={aid}', new_tab=True),
                                ).props('flat dense').tooltip('Open a printable label for this asset')

                # --- Actions ---
                with ui.row().classes('q-mt-md gap-2'):
                    if open_loan is None and can_checkout and asset.status.value != 'retired':
                        label = 'Check out…' if can_manage else 'Check out to me'
                        ui.button(label, icon='logout', on_click=do_checkout).props('color=primary')
                    if open_loan is not None and can_checkin:
                        ui.button('Check in', icon='login', on_click=do_checkin).props('color=secondary')
                    if can_manage:
                        ui.button('Edit', icon='edit', on_click=edit_asset).props('flat')

                # --- History ---
                if history:
                    ui.separator().classes('separator-spacing')
                    ui.label('Loan history').classes('section-title q-mt-md')
                    with ui.column().classes('gap-1 w-full'):
                        for loan in history:
                            out = format_eastern_display(loan.checked_out_at)
                            back = (
                                format_eastern_display(loan.checked_in_at)
                                if loan.checked_in_at else 'still out'
                            )
                            ui.label(
                                f'{loan.borrower.preferred_name}: {out} → {back} '
                                f'(out by {loan.checked_out_by.preferred_name})'
                            ).classes('text-caption')

        async def do_checkout():
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            await open_checkout(actor, asset_id, can_manage=can_manage, on_done=render_detail.refresh)

        async def do_checkin():
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            await quick_checkin(actor, asset_id, on_done=render_detail.refresh)

        async def edit_asset():
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            asset = await service.get_asset(asset_id)
            if asset is None:
                ui.notify('Asset not found.', color='warning')
                return
            await EquipmentDialog(actor, equipment=asset, on_saved=render_detail.refresh).open()

        await render_detail()
