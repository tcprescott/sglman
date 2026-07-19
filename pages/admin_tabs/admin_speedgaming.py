"""Admin SpeedGaming Page — SG schedule ETL config + observability (SYNC_ADMIN/STAFF).

Tenant-scoped CRUD for :class:`~models.SpeedGamingEventLink` (which SG event slug
feeds which tournament), plus each link's sync health (last-synced, status, error)
and an on-demand "Sync now". The background worker runs the same ETL on a cadence
as the system user; this surface is the human-driven half.
"""

from nicegui import app, background_tasks, context, ui
from theme.notify import notify_error
from theme.tables.admin_crud import wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid

from application.services import (
    SpeedGamingSyncService,
    TournamentService,
    get_user_from_discord_id,
)

_ROW_ACTIONS = '''
    <q-btn flat round dense icon="sync" color="primary"
           @click="$parent.$emit('sync_now', props.row)">
        <q-tooltip>Sync now</q-tooltip>
    </q-btn>
    <q-btn flat round dense icon="edit" color="primary"
           @click="$parent.$emit('edit', props.row)">
        <q-tooltip>Edit</q-tooltip>
    </q-btn>
    <q-btn flat round dense icon="delete" color="negative"
           @click="$parent.$emit('delete', props.row)">
        <q-tooltip>Delete</q-tooltip>
    </q-btn>
'''
_ACTIVE_ICON = '''
    <q-icon :name="props.row.active_bool ? 'check_circle' : 'cancel'"
            :color="props.row.active_bool ? 'positive' : 'negative'" size="sm" />
'''
_LAST_STATUS_CHIP = '''
    <span v-if="!props.row.last_status || props.row.last_status === '—'" class="text-grey-7">—</span>
    <span v-else class="sgl-chip"
          :class="props.row.last_status === 'ok' ? 'sgl-chip--ok' : 'sgl-chip--cancelled'">
        {{ props.row.last_status }}
    </span>
'''


async def admin_speedgaming_page() -> None:
    service = SpeedGamingSyncService()
    tournament_service = TournamentService()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('SpeedGaming Sync').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'One-way sync of SpeedGaming schedule episodes into match rows. Each '
            'link maps an SG event slug to a tournament; the sync materializes '
            'episodes into matches (players resolved, placeholders where '
            'unmatched). Synced fields — schedule, players, tournament — are '
            'read-only on the match; everything you add on top stays editable.'
        ).classes('text-caption text-grey')

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
            {'name': 'event_slug', 'label': 'Event Slug', 'field': 'event_slug', 'sortable': True},
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
            {'name': 'active', 'label': 'Active', 'field': 'active'},
            {'name': 'last_synced', 'label': 'Last Synced', 'field': 'last_synced'},
            {'name': 'last_status', 'label': 'Status', 'field': 'last_status'},
            {'name': 'last_error', 'label': 'Error', 'field': 'last_error'},
            {'name': 'actions', 'label': '', 'field': 'actions'},
        ]

        table_container = ui.column().classes('w-full')

        async def _current():
            return await get_user_from_discord_id(app.storage.user.get('discord_id'))

        async def _tournament_options():
            tournaments = await tournament_service.get_all_tournaments()
            return {t.id: t.name for t in tournaments}

        async def refresh_table():
            from application.utils.timezone import format_eastern_display
            links = await service.list_links(await _current())
            table.rows = [
                {
                    'id': link.id,
                    'event_slug': link.event_slug,
                    'tournament': link.tournament.name if link.tournament else '',
                    'tournament_id': link.tournament_id,
                    'content_type': link.content_type or '',
                    'sync_interval_minutes': link.sync_interval_minutes,
                    'lookahead_hours': link.lookahead_hours,
                    'active': 'yes' if link.active else 'no',
                    'active_bool': link.active,
                    'last_synced': format_eastern_display(link.last_synced_at) if link.last_synced_at else '—',
                    'last_status': link.last_status or '—',
                    'last_error': (link.last_error or '')[:80],
                }
                for link in links
            ]
            table.update()

        async def delete_link(row, client):
            with client:
                try:
                    await service.delete_link(await _current(), row['id'])
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Event link deleted', color='positive')
                await refresh_table()

        async def sync_now(row, client):
            with client:
                try:
                    result = await service.sync_now(await _current(), row['id'])
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                if result.errors:
                    ui.notify(
                        f"Sync finished with {result.errors} error(s); "
                        f"{result.imported} imported", color='warning',
                    )
                else:
                    ui.notify(
                        f"Synced: {result.imported} imported, {result.skipped} skipped, "
                        f"{result.cancelled} cancelled", color='positive',
                    )
                await refresh_table()

        async def open_link_dialog(existing=None) -> None:
            is_edit = existing is not None
            options = await _tournament_options()
            with table_container:
                with ui.dialog() as dialog, ui.card().classes('w-[32rem]'):
                    ui.label('Edit Event Link' if is_edit else 'Add Event Link').classes('text-h6')
                    tournament_select = ui.select(
                        options, label='Tournament',
                        value=existing['tournament_id'] if is_edit else None,
                    ).classes('w-full')
                    if is_edit:
                        tournament_select.disable()  # a link's tournament is fixed
                    slug_input = ui.input(
                        'Event Slug', value=existing['event_slug'] if is_edit else '',
                    ).classes('w-full')
                    content_type_input = ui.input(
                        'Content Type (optional)',
                        value=existing['content_type'] if is_edit else '',
                    ).classes('w-full')
                    with ui.row().classes('gap-2'):
                        interval_input = ui.number(
                            'Sync interval (min)',
                            value=existing['sync_interval_minutes'] if is_edit else 15, min=1,
                        ).props('inputmode=numeric')
                        lookahead_input = ui.number(
                            'Lookahead (h)',
                            value=existing['lookahead_hours'] if is_edit else 72, min=1,
                        ).props('inputmode=numeric')
                    active_switch = ui.switch(
                        'Active', value=existing['active_bool'] if is_edit else True,
                    )

                    async def submit():
                        try:
                            current = await _current()
                            if is_edit:
                                await service.update_link(
                                    current, existing['id'],
                                    event_slug=slug_input.value,
                                    content_type=content_type_input.value,
                                    sync_interval_minutes=int(interval_input.value or 15),
                                    lookahead_hours=int(lookahead_input.value or 72),
                                    active=active_switch.value,
                                )
                                ui.notify('Event link updated', color='positive')
                            else:
                                if not tournament_select.value:
                                    ui.notify('Select a tournament', color='warning')
                                    return
                                await service.create_link(
                                    current,
                                    tournament_id=tournament_select.value,
                                    event_slug=slug_input.value,
                                    content_type=content_type_input.value,
                                    sync_interval_minutes=int(interval_input.value or 15),
                                    lookahead_hours=int(lookahead_input.value or 72),
                                    active=active_switch.value,
                                )
                                ui.notify('Event link created', color='positive')
                            dialog.close()
                            await refresh_table()
                        except (ValueError, PermissionError) as e:
                            notify_error(e)

                    with ui.row().classes('justify-end w-full'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button(
                            'Save' if is_edit else 'Add', icon='save' if is_edit else 'add',
                            on_click=submit,
                        ).props('color=primary')
            dialog.open()

        with table_container:
            with ui.row().classes('full-width'):
                ui.button(
                    'Add Event Link', icon='add',
                    on_click=lambda: background_tasks.create(open_link_dialog()),
                ).props('color=primary')
                ui.space()
                ui.button(
                    icon='refresh', on_click=lambda: background_tasks.create(refresh_table()),
                ).props('flat color=primary').tooltip('Refresh table')

            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full sgl-table')

            table.add_slot('body-cell-active', f'<q-td :props="props">{_ACTIVE_ICON}</q-td>')
            table.add_slot('body-cell-last_status', f'<q-td :props="props">{_LAST_STATUS_CHIP}</q-td>')
            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
            enable_mobile_grid(table, columns, actions=_ROW_ACTIONS,
                               field_slots={'active': _ACTIVE_ICON, 'last_status': _LAST_STATUS_CHIP})

            table.on('edit', lambda e: background_tasks.create(open_link_dialog(e.args)))
            table.on('delete', lambda e: background_tasks.create(delete_link(e.args, context.client)))
            table.on('sync_now', lambda e: background_tasks.create(sync_now(e.args, context.client)))

        wire_tab_refresh('SpeedGaming', refresh_table)
        background_tasks.create(refresh_table())
