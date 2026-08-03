"""Admin Payouts Page — prize pool and placement splits per tournament."""

import json
from decimal import Decimal, InvalidOperation

from nicegui import app, background_tasks, context, ui

from application.services import PayoutService, TournamentService, get_user_from_discord_id
from application.services.payout_service import format_percentage
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.notify import notify_error
from theme.tables.admin_crud import refresh_button, wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys

_STATUS_CHIP = '''
    <span class="wiz-chip" :class="props.row.status_chip">{{ props.row.status }}</span>
'''

_ROW_ACTIONS = '''
    <q-btn flat round dense icon="payments" color="primary"
           @click="$parent.$emit('pool', props.row)">
        <q-tooltip>Prize pool</q-tooltip>
    </q-btn>
    <q-btn flat round dense icon="leaderboard" color="primary"
           @click="$parent.$emit('split', props.row)">
        <q-tooltip>Edit split</q-tooltip>
    </q-btn>
    <q-btn flat round dense icon="content_copy" color="primary"
           @click="$parent.$emit('copy', props.row)">
        <q-tooltip>Copy for Matcherino</q-tooltip>
    </q-btn>
'''


def _money(value: Decimal) -> str:
    return f'${value:,.2f}'


def _parse_money(raw: str | None, label: str) -> Decimal | None:
    text = (raw or '').strip().lstrip('$').replace(',', '')
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f'{label} must be a number, or blank.')


def _parse_percentage(raw: str | None) -> Decimal:
    text = (raw or '').strip().rstrip('%')
    if not text:
        raise ValueError('Every place needs a share.')
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f'{text!r} is not a percentage.')


def _status(overview) -> dict:
    """What is still missing on this tournament's split, in one chip."""
    if not overview.place_count:
        return {'status': 'No split', 'status_chip': ''}
    if not overview.is_complete:
        return {'status': 'Winners not named', 'status_chip': 'wiz-chip--pending'}
    return {'status': 'Ready', 'status_chip': 'wiz-chip--ok'}


async def admin_payouts_page() -> None:
    service = PayoutService()
    tournament_service = TournamentService()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Payouts').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'Record what each placement wins as a share of the pool. Amounts are '
            'worked out from the pool and the bonus every time they are read, so '
            'moving the pool moves every share with it.'
        ).classes('text-caption text-grey')

        columns = [
            {'name': 'tournament_id', 'label': 'ID', 'field': 'tournament_id', 'hidden': True},
            {'name': 'name', 'label': 'Tournament', 'field': 'name', 'sortable': True},
            # The money columns sort on their numeric ``*_raw`` field and render
            # through a cell slot, so Pool orders 9 before 10 rather than
            # alphabetically on "$10.00".
            {'name': 'pool', 'label': 'Pool', 'field': 'pool_raw', 'sortable': True},
            {'name': 'bonus', 'label': 'Bonus', 'field': 'bonus_raw', 'sortable': True},
            {'name': 'total', 'label': 'Total', 'field': 'total_raw', 'sortable': True},
            {'name': 'places', 'label': 'Places', 'field': 'place_count', 'sortable': True},
            {'name': 'allocated', 'label': 'Allocated', 'field': 'allocated_raw',
             'sortable': True},
            {'name': 'status', 'label': 'Status', 'field': 'status'},
            {'name': 'actions', 'label': '', 'field': 'actions'},
        ]
        table_container = ui.column().classes('w-full')

        async def _current():
            return await get_user_from_discord_id(app.storage.user.get('discord_id'))

        async def refresh_table():
            actor = await _current()
            overviews = await service.list_overview(actor)
            table.rows = [
                {
                    'tournament_id': o.tournament_id,
                    'name': o.name,
                    'pool_raw': float(o.pool),
                    'bonus_raw': float(o.bonus),
                    'total_raw': float(o.total),
                    'pool': _money(o.pool),
                    'bonus': _money(o.bonus),
                    'total': _money(o.total),
                    'place_count': o.place_count,
                    'allocated_raw': float(o.allocated_percentage),
                    'allocated': f'{format_percentage(o.allocated_percentage)}%',
                    **_status(o),
                }
                for o in overviews
            ]
            table.update()

        async def open_pool_dialog(row, client):
            with client:
                try:
                    split = await service.get_split(row['tournament_id'], await _current())
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                with table_container:
                    with form_dialog(f"Prize pool — {row['name']}") as dialog:
                        with ui.column().classes('q-pa-md gap-2 full-width'):
                            pool_input = ui.input(
                                'Prize pool', value=f'{split.pool:.2f}',
                            ).props('outlined dense prefix="$"').classes('w-full')
                            bonus_input = ui.input(
                                'Bonus', value=f'{split.bonus:.2f}',
                            ).props('outlined dense prefix="$"').classes('w-full')
                            ui.label(
                                'Shares are taken from the pool and the bonus added '
                                'together. Leave a field blank if nobody has decided it yet.'
                            ).classes('text-caption text-grey')

                        async def submit():
                            try:
                                await service.set_pool(
                                    row['tournament_id'],
                                    _parse_money(pool_input.value, 'Prize pool'),
                                    _parse_money(bonus_input.value, 'Bonus'),
                                    await _current(),
                                )
                            except (ValueError, PermissionError) as e:
                                notify_error(e)
                                return
                            dialog.close()
                            ui.notify('Prize pool saved', color='positive')
                            await refresh_table()

                        with dialog_actions().classes('justify-end'):
                            ui.button('Cancel', on_click=dialog.close).props('flat')
                            ui.button('Save', icon='save', on_click=submit).props('color=primary')
                dialog.open()

        async def open_split_dialog(row, client):
            with client:
                actor = await _current()
                try:
                    split = await service.get_split(row['tournament_id'], actor)
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                entrants = await tournament_service.get_enrolled_players_by_tournament_id(
                    row['tournament_id']
                )
                options: dict[int | None, str] = {None: '(not decided yet)'}
                for tp in entrants:
                    options[tp.user_id] = tp.user.preferred_name
                for line in split.lines:
                    if line.entrant is not None:
                        options.setdefault(line.entrant.id, line.entrant.preferred_name)

                # Widgets keyed by an incrementing id rather than by index, so
                # removing a middle row cannot renumber the rows below it.
                widgets: dict[int, dict] = {}
                next_key = {'n': 0}

                with table_container:
                    with form_dialog(f"Split — {row['name']}") as dialog:
                        with ui.column().classes('q-pa-md gap-2 full-width'):
                            ui.label(
                                f'Sharing {_money(split.total)}. Two rows may hold the '
                                'same place — joint placings are paid separately, not '
                                'halved.'
                            ).classes('text-caption text-grey')
                            rows_column = ui.column().classes('w-full gap-2')

                            def add_row(place=1, percentage='', entrant_id=None):
                                key = next_key['n']
                                next_key['n'] += 1
                                with rows_column:
                                    with ui.row().classes('items-center w-full no-wrap gap-2') as holder:
                                        place_input = ui.number(
                                            'Place', value=place, min=1, format='%d',
                                        ).props('outlined dense').style('width: 6rem')
                                        pct_input = ui.input(
                                            'Share', value=str(percentage),
                                        ).props('outlined dense suffix="%"').style('width: 7rem')
                                        entrant_select = ui.select(
                                            options, value=entrant_id, label='Winner',
                                            with_input=True,
                                        ).props('outlined dense').classes('col min-w-0')

                                        def remove():
                                            holder.delete()
                                            widgets.pop(key, None)

                                        ui.button(icon='delete', on_click=remove) \
                                            .props('flat dense round color=negative') \
                                            .tooltip('Remove this place')
                                widgets[key] = {
                                    'place': place_input,
                                    'percentage': pct_input,
                                    'entrant': entrant_select,
                                }

                            for line in split.lines:
                                add_row(
                                    line.place, format_percentage(line.percentage),
                                    line.entrant.id if line.entrant else None,
                                )
                            if not split.lines:
                                add_row(1, '')

                            ui.button('Add place', icon='add',
                                      on_click=lambda: add_row(len(widgets) + 1, '')) \
                                .props('flat color=primary')

                        async def submit():
                            payload = []
                            try:
                                for entry in widgets.values():
                                    payload.append({
                                        'place': int(entry['place'].value or 0),
                                        'percentage': _parse_percentage(entry['percentage'].value),
                                        'entrant_id': entry['entrant'].value,
                                    })
                                await service.set_split(
                                    row['tournament_id'], payload, await _current(),
                                )
                            except (ValueError, PermissionError) as e:
                                notify_error(e)
                                return
                            dialog.close()
                            ui.notify('Split saved', color='positive')
                            await refresh_table()

                        with dialog_actions().classes('justify-end'):
                            ui.button('Cancel', on_click=dialog.close).props('flat')
                            ui.button('Save', icon='save', on_click=submit).props('color=primary')
                dialog.open()

        async def copy_block(row, client):
            with client:
                try:
                    block = await service.export_block(row['tournament_id'], await _current())
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.run_javascript(f'navigator.clipboard.writeText({json.dumps(block)})')
                ui.notify('Payout block copied to clipboard.', color='positive',
                          icon='content_copy')

        with table_container:
            with ui.row().classes('full-width'):
                ui.space()
                refresh_button(refresh_table)

            table = ui.table(columns=columns, rows=[], row_key='tournament_id') \
                .classes('w-full wiz-table')

            table.add_slot('body-cell-pool', '<q-td :props="props">{{ props.row.pool }}</q-td>')
            table.add_slot('body-cell-bonus', '<q-td :props="props">{{ props.row.bonus }}</q-td>')
            table.add_slot('body-cell-total', '<q-td :props="props">{{ props.row.total }}</q-td>')
            table.add_slot('body-cell-allocated',
                           '<q-td :props="props">{{ props.row.allocated }}</q-td>')
            table.add_slot('body-cell-status', f'<q-td :props="props">{_STATUS_CHIP}</q-td>')
            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')

            table.on('pool', lambda e: background_tasks.create(
                open_pool_dialog(e.args, context.client)))
            table.on('split', lambda e: background_tasks.create(
                open_split_dialog(e.args, context.client)))
            table.on('copy', lambda e: background_tasks.create(
                copy_block(e.args, context.client)))

            enable_mobile_grid(
                table, columns, actions=_ROW_ACTIONS,
                table_key=TableKeys.ADMIN_PAYOUTS,
                field_slots={
                    'pool': '{{ props.row.pool }}',
                    'bonus': '{{ props.row.bonus }}',
                    'total': '{{ props.row.total }}',
                    'allocated': '{{ props.row.allocated }}',
                    'status': _STATUS_CHIP,
                },
            )

        wire_tab_refresh('Payouts', refresh_table)
        background_tasks.create(refresh_table())
