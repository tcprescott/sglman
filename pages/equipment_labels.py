"""Bulk equipment QR-label sheet — a printable Letter grid of asset QR codes.

Reached from the admin Equipment tab's "Print QR labels" flow (see
``theme/dialog/qr_label_dialog.py``): the selected asset ids arrive as a
comma-separated ``ids`` query param and each asset is rendered as a label
(scannable QR + ``#number`` + name) in a CSS grid sized to US Letter. The
manager prints the page from the browser (the toolbar's Print button, or
Ctrl/Cmd-P). The toolbar is hidden in print via a ``.no-print`` rule.

Manager-only (Staff / Equipment Manager), gated behind ``FeatureFlag.EQUIPMENT``
like the rest of the equipment surface. Each QR encodes the asset's own
tenant-qualified detail URL, exactly as the single-asset page does.
"""

from nicegui import ui

from middleware.auth import protected_page

from application.services import EquipmentService, TenantService
from application.tenant_context import get_current_tenant_id
from application.utils.environment import get_base_url
from application.utils.qrcode_util import asset_qr_data_uri
from application.utils.tenant_urls import tenant_url
from models import FeatureFlag, Role

# Printing is the whole point of the page, so the styles below cannot be
# expressed as Quasar utility classes: @page sizes the sheet to Letter, and the
# @media print block drops the app's screen-only toolbar from the printout.
# add_head_html(shared=False) keeps these scoped to this page's clients.
_PRINT_CSS = """
<style>
@page { size: letter; margin: 0.5in; }
.qr-labels-toolbar { gap: 0.75rem; }
.qr-sheet {
    display: grid;
    gap: 0.2in;
    width: 100%;
    box-sizing: border-box;
}
.qr-label {
    break-inside: avoid;
    page-break-inside: avoid;
    border: 1px dashed #b0b0b0;
    border-radius: 8px;
    padding: 10px 8px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 4px;
}
.qr-label .qr-code-img { width: 100%; max-width: 1.7in; height: auto; }
/* keep the QR crisp when scaled up for the label — scannability */
.qr-label .qr-code-img img { image-rendering: pixelated; }
.qr-label .qr-num { font-weight: 700; font-size: 0.95rem; }
.qr-label .qr-name { font-size: 0.8rem; line-height: 1.15; word-break: break-word; }
@media print {
    .no-print { display: none !important; }
    .qr-label { border-color: #888; }
}
</style>
"""

_MIN_COLS, _MAX_COLS, _DEFAULT_COLS = 1, 5, 3


def _parse_ids(raw: str) -> list[int]:
    """Comma-separated id string → list of ints, dropping blanks / non-numerics."""
    out: list[int] = []
    for part in (raw or '').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def create() -> None:
    @protected_page(
        '/equipment/qr-labels',
        roles=[Role.STAFF, Role.EQUIPMENT_MANAGER],
        feature=FeatureFlag.EQUIPMENT,
    )
    async def equipment_qr_labels(ids: str = '', cols: int = _DEFAULT_COLS) -> None:
        community = await TenantService.current_community_name() or 'Wizzrobe'
        ui.page_title(f'{community} — QR labels')
        ui.add_head_html(_PRINT_CSS)

        assets = await EquipmentService().get_assets_by_ids(_parse_ids(ids))

        # Tenant-qualified deep link per asset, matching the single-asset page:
        # the custom domain when set, else the path-mode /t/<slug>/… form.
        tid = get_current_tenant_id()
        tenant = await TenantService.get_by_id(tid) if tid is not None else None

        def asset_link(asset) -> str:
            if tenant is not None:
                return tenant_url(tenant, f'/equipment/{asset.id}')
            return f'{get_base_url()}/equipment/{asset.id}'

        # Pre-render each label once (QR generation is the expensive part) so the
        # columns toggle only re-lays-out cached cells rather than re-encoding.
        labels = [
            (f'#{asset.asset_number}', asset.name or '', asset_qr_data_uri(asset_link(asset)))
            for asset in assets
        ]

        try:
            columns = max(_MIN_COLS, min(int(cols), _MAX_COLS))
        except (TypeError, ValueError):
            columns = _DEFAULT_COLS
        state = {'cols': columns}

        with ui.row().classes('qr-labels-toolbar no-print items-center full-width q-pa-sm'):
            ui.label(f'{community} — equipment QR labels').classes('text-h6 q-ma-none')
            ui.space()
            if labels:
                ui.label(f'{len(labels)} label{"s" if len(labels) != 1 else ""}').classes('text-caption')
                ui.toggle(
                    {2: '2', 3: '3', 4: '4'},
                    value=state['cols'] if state['cols'] in (2, 3, 4) else 3,
                    on_change=lambda e: _set_cols(int(e.value)),
                ).props('dense').tooltip('Columns per row')
                ui.button(
                    'Print', icon='print',
                    on_click=lambda: ui.run_javascript('window.print()'),
                ).props('color=primary')

        if not labels:
            ui.label('No equipment selected to print.').classes('text-error q-pa-md')
            return

        @ui.refreshable
        def sheet() -> None:
            with ui.element('div').classes('qr-sheet').style(
                f'grid-template-columns: repeat({state["cols"]}, 1fr)'
            ):
                for num, name, uri in labels:
                    with ui.element('div').classes('qr-label'):
                        # loading=eager so QR labels below the fold are decoded
                        # before print rather than lazy-loaded on scroll.
                        ui.image(uri).props('loading=eager no-spinner no-transition').classes('qr-code-img')
                        ui.label(num).classes('qr-num')
                        ui.label(name).classes('qr-name')

        def _set_cols(value: int) -> None:
            state['cols'] = max(_MIN_COLS, min(value, _MAX_COLS))
            sheet.refresh()

        sheet()
