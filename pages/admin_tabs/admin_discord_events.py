"""Admin Discord Events Page — schedule → Discord Scheduled Events mirror (SYNC_ADMIN/STAFF).

Per-tournament opt-in for mirroring scheduled matches into the tenant guild's
Discord Scheduled Events, plus an on-demand "Sync now" and an observability table
of the events this tenant currently owns. The background reconciler runs the same
reconcile on a cadence as the system user; this surface is the human-driven half.
The mirror needs a **linked Discord server** — the page surfaces that up front.
"""

from nicegui import app, background_tasks, context, ui
from theme.notify import notify_error

from application.services import (
    DiscordEventSyncService,
    get_user_from_discord_id,
)


async def admin_discord_events_page() -> None:
    service = DiscordEventSyncService()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Discord Events').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'Mirror scheduled matches into your Discord server\'s Scheduled Events. '
            'Enable per tournament below; the reconciler creates, updates, and '
            'cancels events to match your schedule. It only ever touches events it '
            'created, so sharing a Discord server with another community is safe.'
        ).classes('text-caption text-grey')

        link_banner = ui.row().classes('w-full items-center')

        async def _current():
            return await get_user_from_discord_id(app.storage.user.get('discord_id'))

        async def refresh_link_banner():
            link_banner.clear()
            tenant = await service.get_tenant()
            with link_banner:
                if tenant is not None and tenant.discord_guild_id is not None:
                    ui.icon('check_circle', color='positive')
                    ui.label('A Discord server is connected — events will sync.').classes('text-caption')
                else:
                    ui.icon('warning', color='warning')
                    ui.label(
                        'No Discord server connected. Connect one from the Discord Roles '
                        'tab before events can sync.'
                    ).classes('text-caption')

        # --- Per-tournament opt-in ------------------------------------------
        ui.label('Tournaments').classes('section-title q-mt-md')
        tournament_columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
            {'name': 'name', 'label': 'Tournament', 'field': 'name', 'sortable': True},
            {'name': 'enabled', 'label': 'Events synced', 'field': 'enabled'},
            {'name': 'duration', 'label': 'Duration (min)', 'field': 'duration'},
            {'name': 'actions', 'label': '', 'field': 'actions'},
        ]
        tournaments_container = ui.column().classes('w-full')

        # --- Mirrored events (observability) --------------------------------
        ui.label('Mirrored events').classes('section-title q-mt-md')
        event_columns = [
            {'name': 'title', 'label': 'Title', 'field': 'title', 'sortable': True},
            {'name': 'when', 'label': 'When', 'field': 'when'},
            {'name': 'discord_event_id', 'label': 'Discord Event', 'field': 'discord_event_id'},
            {'name': 'synced', 'label': 'Synced', 'field': 'synced'},
        ]
        events_container = ui.column().classes('w-full')

        async def refresh_tables():
            from application.utils.timezone import format_eastern_display
            user = await _current()
            tournaments = await service.list_tournaments(user)
            tournament_table.rows = [
                {
                    'id': t.id,
                    'name': t.name,
                    'enabled': 'yes' if t.discord_events_enabled else 'no',
                    'enabled_bool': t.discord_events_enabled,
                    'duration': t.discord_event_duration_minutes,
                    'title_template': t.discord_event_title_template or '',
                    'description_template': t.discord_event_description_template or '',
                }
                for t in tournaments
            ]
            tournament_table.update()

            events = await service.list_events(user)
            event_table.rows = [
                {
                    'title': e.title,
                    'when': format_eastern_display(e.scheduled_at) if e.scheduled_at else '—',
                    'discord_event_id': str(e.discord_event_id),
                    'synced': format_eastern_display(e.synced_at) if e.synced_at else '—',
                }
                for e in events
            ]
            event_table.update()

        async def sync_now(client):
            with client:
                try:
                    result = await service.reconcile_now(await _current())
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                if result.errors:
                    ui.notify(
                        f"Sync finished with {result.errors} error(s); "
                        f"{result.created} created, {result.updated} updated",
                        color='warning',
                    )
                else:
                    ui.notify(
                        f"Synced: {result.created} created, {result.updated} updated, "
                        f"{result.cancelled} cancelled", color='positive',
                    )
                await refresh_tables()

        async def open_settings_dialog(row, client) -> None:
            with tournaments_container:
                with ui.dialog() as dialog, ui.card().classes('w-[32rem]'):
                    ui.label(f"Discord events — {row['name']}").classes('text-h6')
                    enabled_switch = ui.switch('Sync this tournament\'s matches', value=row['enabled_bool'])
                    duration_input = ui.number(
                        'Event duration (min)', value=row['duration'], min=1,
                    ).props('inputmode=numeric').classes('w-full')
                    title_input = ui.input(
                        'Title template (optional)', value=row['title_template'],
                    ).classes('w-full')
                    desc_input = ui.input(
                        'Description template (optional)', value=row['description_template'],
                    ).classes('w-full')
                    ui.label(
                        'Placeholders: {tournament}, {match}, {players}'
                    ).classes('text-caption text-grey')

                    async def submit():
                        try:
                            await service.update_settings(
                                await _current(), row['id'],
                                enabled=enabled_switch.value,
                                duration_minutes=int(duration_input.value or 60),
                                title_template=title_input.value,
                                description_template=desc_input.value,
                            )
                            ui.notify('Settings saved', color='positive')
                            dialog.close()
                            await refresh_tables()
                        except (ValueError, PermissionError) as e:
                            notify_error(e)

                    with ui.row().classes('justify-end w-full'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button('Save', icon='save', on_click=submit).props('color=primary')
            dialog.open()

        with tournaments_container:
            with ui.row().classes('full-width'):
                ui.button(
                    'Sync now', icon='sync',
                    on_click=lambda: background_tasks.create(sync_now(context.client)),
                ).props('color=primary')
                ui.space()
                ui.button(
                    icon='refresh', on_click=lambda: background_tasks.create(refresh_tables()),
                ).props('flat color=primary').tooltip('Refresh')

            tournament_table = ui.table(columns=tournament_columns, rows=[], row_key='id').classes('w-full sgl-table')
            tournament_table.add_slot('body-cell-enabled', '''
                <q-td :props="props">
                    <q-icon :name="props.row.enabled_bool ? 'check_circle' : 'cancel'"
                            :color="props.row.enabled_bool ? 'positive' : 'negative'" size="sm" />
                </q-td>
            ''')
            tournament_table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn flat round dense icon="edit" color="primary"
                           @click="$parent.$emit('edit', props.row)">
                        <q-tooltip>Edit</q-tooltip>
                    </q-btn>
                </q-td>
            ''')
            tournament_table.on('edit', lambda e: background_tasks.create(open_settings_dialog(e.args, context.client)))

        with events_container:
            event_table = ui.table(columns=event_columns, rows=[], row_key='discord_event_id').classes('w-full sgl-table')

        ui.on('selected_tab', lambda e: background_tasks.create(refresh_tables()) if e.args == 'Discord Events' else None)
        background_tasks.create(refresh_link_banner())
        background_tasks.create(refresh_tables())
