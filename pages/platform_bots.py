"""The Racetime Bots section of ``/platform``.

Split out of ``pages/platform.py`` the way ``platform_tenant_admins`` was: the
page stacks four independent sections and kept running at the file-length
guideline, so each section that can stand alone does.

Bots are platform-managed and shared: one per racetime category, granted to
tenants whose sync admins then select them on a tournament. Client secrets are
write-only — the form takes one, nothing ever renders it back.
"""

from nicegui import ui

from application.services import RacetimeBotService, TenantService
from pages.platform_shared import ACTIVE_ICON_SLOT, current_actor
from theme.tables.preferences import TableKeys, customize_table, preferences_button

_bot_service = RacetimeBotService()

# Colored bot-health chip, shared by the desktop status cell and the mobile card
# so the two never drift. Rows must carry ``status`` (text) and ``status_kind``.
_BOT_STATUS_CHIP = '''
    <span class="wiz-chip" :class="{
        'wiz-chip--ok': props.row.status_kind === 'connected',
        'wiz-chip--cancelled': props.row.status_kind === 'error' || props.row.status_kind === 'disconnected',
        'wiz-chip--neutral': props.row.status_kind === 'unknown'
    }">{{ props.row.status }}</span>
'''


async def render_bots_section(user) -> None:
    """Build the bots table, wire its row actions, and load it."""
    with ui.row().classes('w-full items-center justify-between'):
        ui.label('Racetime Bots').classes('section-title')
        with ui.row().classes('items-center gap-2'):
            bot_header_row = ui.row().classes('items-center')
            ui.button('New bot', icon='add', on_click=lambda: _open_bot_create_dialog(user, bot_table)).props('color=primary')
    ui.label(
        'Shared, platform-managed bots — one per racetime category. Grant a '
        "bot to a tenant to let its sync admins select it on a tournament. "
        'Client secrets are write-only and never shown.'
    ).classes('text-caption text-grey')

    bot_columns: list[dict] = [
        {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
        {'name': 'category', 'label': 'Category', 'field': 'category', 'align': 'left', 'sortable': True},
        {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
        {'name': 'client_id', 'label': 'Client ID', 'field': 'client_id', 'align': 'left'},
        {'name': 'active', 'label': 'Active', 'field': 'active', 'align': 'left'},
        {'name': 'status', 'label': 'Health', 'field': 'status', 'align': 'left'},
        {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
    ]
    bot_table = ui.table(columns=bot_columns, rows=[], row_key='id').classes(
        'w-full wiz-table').props(':grid="Quasar.Screen.lt.md"')
    bot_table.add_slot('body-cell-active', ACTIVE_ICON_SLOT)
    bot_table.add_slot('body-cell-status', f'<q-td :props="props">{_BOT_STATUS_CHIP}</q-td>')
    bot_table.add_slot('body-cell-actions', '''
        <q-td :props="props">
            <q-btn dense flat color="primary" label="Edit"
                   @click="$parent.$emit('edit_bot', props.row)" />
            <q-btn dense flat color="secondary" label="Tenants"
                   @click="$parent.$emit('grant_bot', props.row)" />
            <q-btn dense flat color="orange" label="Restart"
                   @click="$parent.$emit('restart_bot', props.row)" />
        </q-td>
    ''')
    bot_table.add_slot('item', '''
        <div class="q-pa-xs col-xs-12 col-sm-6">
            <q-card bordered flat class="q-pa-sm wiz-grid-card">
                <div class="row items-center justify-between no-wrap q-mb-xs">
                    <div class="text-weight-bold">{{ props.row.category }}</div>
                    <q-icon :name="props.row.active_bool ? 'check_circle' : 'cancel'"
                            :color="props.row.active_bool ? 'positive' : 'negative'" size="sm">
                        <q-tooltip>{{ props.row.active_bool ? 'Active' : 'Inactive' }}</q-tooltip>
                    </q-icon>
                </div>
                <div class="text-caption text-grey-7 q-mb-xs">#{{ props.row.id }} · {{ props.row.name }}</div>
                <div class="row q-mb-xs">
                    <div class="col-4 text-grey-7 text-caption">Client ID</div>
                    <div class="col-8" style="overflow-wrap:anywhere">{{ props.row.client_id }}</div>
                </div>
                <div class="row items-center q-mb-xs">
                    <div class="col-4 text-grey-7 text-caption">Health</div>
                    <div class="col-8">''' + _BOT_STATUS_CHIP + '''</div>
                </div>
                <div class="row justify-end q-gutter-x-sm q-mt-xs">
                    <q-btn dense flat color="primary" label="Edit"
                           @click="$parent.$emit('edit_bot', props.row)" />
                    <q-btn dense flat color="secondary" label="Tenants"
                           @click="$parent.$emit('grant_bot', props.row)" />
                    <q-btn dense flat color="orange" label="Restart"
                           @click="$parent.$emit('restart_bot', props.row)" />
                </div>
            </q-card>
        </div>
    ''')

    customize_table(bot_table, bot_columns, key=TableKeys.PLATFORM_RACETIME_BOTS)
    with bot_header_row:
        preferences_button(bot_table)

    async def _on_edit_bot(e) -> None:
        await _open_bot_edit_dialog(user, bot_table, e.args)

    async def _on_grant_bot(e) -> None:
        await _open_bot_tenants_dialog(user, e.args)

    async def _on_restart_bot(e) -> None:
        await _restart_bot(user, bot_table, e.args)

    bot_table.on('edit_bot', _on_edit_bot)
    bot_table.on('grant_bot', _on_grant_bot)
    bot_table.on('restart_bot', _on_restart_bot)

    await _refresh_bots(bot_table)


async def _refresh_bots(table) -> None:
    bots = await _bot_service.list_bots(await current_actor())
    table.rows = [
        {
            'id': b.id, 'category': b.category, 'name': b.name,
            'client_id': b.client_id,
            'active': 'yes' if b.is_active else 'no',
            'active_bool': b.is_active,
            # Humanized status ('connected' -> 'Connected'), never the raw
            # 'BotStatus.CONNECTED' repr; message appended when present.
            'status': (
                f'{b.status.value.title()} — {b.status_message}'
                if b.status_message else b.status.value.title()
            ),
            'status_kind': b.status.value,
        }
        for b in bots
    ]
    table.update()


async def _restart_bot(actor, table, row) -> None:
    from racetimebot import get_racetime_manager
    try:
        await get_racetime_manager().restart(actor, row['id'])
    except (ValueError, PermissionError) as e:
        ui.notify(str(e), color='warning')
        return
    ui.notify('Bot connection restarting', color='positive')
    await _refresh_bots(table)



def _bot_form(existing=None):
    """Render the shared bot input widgets; returns them for the submit handler."""
    is_edit = existing is not None
    category = ui.input('Category', value=existing['category'] if is_edit else '').classes('w-full')
    name = ui.input('Name', value=existing['name'] if is_edit else '').classes('w-full')
    client_id = ui.input('Client ID', value=existing['client_id'] if is_edit else '').classes('w-full')
    secret = ui.input('Client Secret').props('type=password').classes('w-full')
    if is_edit:
        secret.props('hint="Leave blank to keep the current secret"')
    description = ui.textarea('Description', value=existing.get('description', '') if is_edit else '').classes('w-full')
    handler = ui.input('Handler class', value=existing.get('handler_class', '') if is_edit else '').classes('w-full')
    active = ui.switch('Active', value=existing['active'] == 'yes' if is_edit else True)
    return category, name, client_id, secret, description, handler, active


def _open_bot_create_dialog(actor, table) -> None:
    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label('New racetime bot').classes('text-lg font-semibold')
        category, name, client_id, secret, description, handler, active = _bot_form()

        async def submit():
            try:
                await _bot_service.create_bot(
                    actor, category=category.value, name=name.value,
                    client_id=client_id.value, client_secret=secret.value,
                    description=description.value, handler_class=handler.value,
                    is_active=active.value,
                )
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Bot created', color='positive')
            dialog.close()
            await _refresh_bots(table)

        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Create', on_click=submit, color='primary')
    dialog.open()


async def _open_bot_edit_dialog(actor, table, row) -> None:
    bot = await _bot_service.get_bot(actor, row['id'])
    existing = _bot_service.serialize(bot)
    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label(f"Edit bot #{bot.id}").classes('text-lg font-semibold')
        # serialize() omits the secret; expose the plain fields to the form.
        existing['active'] = 'yes' if bot.is_active else 'no'
        category, name, client_id, secret, description, handler, active = _bot_form(existing)

        async def submit():
            try:
                await _bot_service.update_bot(
                    actor, bot.id, category=category.value, name=name.value,
                    client_id=client_id.value, client_secret=secret.value,
                    description=description.value, handler_class=handler.value,
                    is_active=active.value,
                )
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Bot updated', color='positive')
            dialog.close()
            await _refresh_bots(table)

        async def delete_bot():
            try:
                await _bot_service.delete_bot(actor, bot.id)
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Bot deleted', color='positive')
            dialog.close()
            await _refresh_bots(table)

        with ui.row().classes('w-full justify-between'):
            ui.button('Delete', on_click=delete_bot, color='negative').props('flat')
            with ui.row():
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=submit, color='primary')
    dialog.open()


async def _open_bot_tenants_dialog(actor, row) -> None:
    bot_id = row['id']
    tenants = await TenantService.list_tenants()
    grants = {g.tenant_id: g for g in await _bot_service.list_grants(actor, bot_id)}
    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label(f"Tenants for {row['category']}").classes('text-lg font-semibold')
        ui.label('Toggle which tenants may select this bot.').classes('text-caption text-grey')

        async def _toggle(tenant_id: int, enabled: bool):
            try:
                if enabled:
                    await _bot_service.grant_tenant(actor, bot_id, tenant_id)
                else:
                    await _bot_service.revoke_tenant(actor, bot_id, tenant_id)
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Updated', color='positive')

        for t in tenants:
            grant = grants.get(t.id)
            ui.switch(
                t.name, value=bool(grant and grant.is_active),
                on_change=lambda e, tid=t.id: _toggle(tid, e.value),
            )

        with ui.row().classes('w-full justify-end'):
            ui.button('Close', on_click=dialog.close).props('flat')
    dialog.open()
