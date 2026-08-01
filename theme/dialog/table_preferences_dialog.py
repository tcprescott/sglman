"""The Preferences modal behind every customizable table's gear.

Staged, not live: every control edits a local copy and **Cancel** discards it, so
half-finished experiments never reach the database — the AWS console's
`CollectionPreferences` shape, which is what this was modelled on.

The ▲/▼ buttons and the width steppers are the keyboard and touch equivalents of
drag-to-reorder and drag-to-resize. They are not a fallback to be removed once
dragging exists: a dialog whose whole purpose is making a table usable must not
itself be mouse-only.
"""

from nicegui import ui

from application.services import TablePreferenceService
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.tables.admin_crud import current_actor
from theme.tables.preferences import apply_saved_config, customization_of

PAGE_SIZE_LABELS = {0: 'All', 10: '10', 25: '25', 50: '50', 100: '100'}
DENSITY_LABELS = {'comfortable': 'Comfortable', 'compact': 'Compact'}


def _staged_columns(custom) -> list[dict]:
    """The dialog's working copy: one entry per column, in the plan's order."""
    visible = set(custom.plan.visible)
    return [
        {
            'name': col.get('name', ''),
            'label': str(col.get('label') or col.get('name', '')) or '(unlabelled)',
            'visible': col.get('name', '') in visible,
            'width': custom.plan.widths.get(col.get('name', '')),
        }
        for col in custom.plan.columns
    ]


def _config_from(staged: list[dict], page_size: int, density: str, wrap: bool) -> dict:
    return {
        'columns': [
            {'name': c['name'], 'visible': bool(c['visible']),
             'width': int(c['width']) if c['width'] else None}
            for c in staged
        ],
        'page_size': page_size,
        'density': density,
        'wrap': wrap,
    }


async def open_table_preferences(table: ui.table) -> None:
    """Open the Preferences dialog for a table already passed to ``customize_table``."""
    custom = customization_of(table)
    if custom is None:
        ui.notify('This table is not customizable.', color='warning')
        return
    actor = await current_actor()
    if actor is None:
        ui.notify('Sign in to save table preferences.', color='warning')
        return

    service = TablePreferenceService()
    staged = _staged_columns(custom)
    state = {
        'page_size': custom.plan.page_size,
        'density': custom.plan.density,
        'wrap': custom.plan.wrap,
    }
    # A table shipped with a page size the radio does not offer (some reports use
    # 15) must still show its current value rather than silently reading as 'All'.
    size_options = dict(PAGE_SIZE_LABELS)
    if state['page_size'] not in size_options:
        size_options[state['page_size']] = str(state['page_size'])

    with form_dialog('Table preferences') as dialog:
        with ui.column().classes('q-pa-md gap-3 full-width'):
            with ui.row().classes('full-width gap-6 items-start'):
                with ui.column().classes('gap-1'):
                    ui.label('Rows per page').classes('text-caption text-grey-7')
                    ui.radio(dict(sorted(size_options.items())),
                             value=state['page_size'],
                             on_change=lambda e: state.update(page_size=e.value)) \
                        .props('inline dense')
                with ui.column().classes('gap-1'):
                    ui.label('Density').classes('text-caption text-grey-7')
                    ui.radio(DENSITY_LABELS, value=state['density'],
                             on_change=lambda e: state.update(density=e.value)) \
                        .props('inline dense')
            ui.switch('Wrap long values', value=state['wrap'],
                      on_change=lambda e: state.update(wrap=e.value))

            ui.separator()
            ui.label('Columns').classes('text-caption text-grey-7')
            column_list = ui.column().classes('full-width gap-0')

        def move(index: int, delta: int) -> None:
            target = index + delta
            if 0 <= target < len(staged):
                staged[index], staged[target] = staged[target], staged[index]
                render_columns()

        def render_columns() -> None:
            column_list.clear()
            with column_list:
                for index, entry in enumerate(staged):
                    required = entry['name'] in custom.required
                    with ui.row().classes('full-width items-center gap-2 q-py-xs'):
                        checkbox = ui.checkbox(
                            value=True if required else entry['visible'],
                            on_change=lambda e, c=entry: c.update(visible=e.value),
                        ).props('dense')
                        if required:
                            # Disabled, not missing: the absence has to explain itself.
                            checkbox.props('disable')
                        ui.label(entry['label']).classes('col-grow')
                        if required:
                            ui.label('Always shown').classes('text-caption text-grey-7')
                        ui.number(
                            value=entry['width'], placeholder='auto',
                            min=TablePreferenceService.MIN_WIDTH,
                            max=TablePreferenceService.MAX_WIDTH,
                            on_change=lambda e, c=entry: c.update(width=e.value),
                        ).props('dense outlined suffix=px').classes('w-24') \
                            .tooltip('Column width in pixels; blank for automatic')
                        ui.button(icon='arrow_upward', on_click=lambda _, i=index: move(i, -1)) \
                            .props('flat dense round').tooltip('Move up') \
                            .set_enabled(index > 0)
                        ui.button(icon='arrow_downward', on_click=lambda _, i=index: move(i, 1)) \
                            .props('flat dense round').tooltip('Move down') \
                            .set_enabled(index < len(staged) - 1)

        render_columns()

        async def confirm() -> None:
            config = _config_from(staged, state['page_size'], state['density'], state['wrap'])
            try:
                saved = await service.save(actor, custom.key, config)
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            apply_saved_config(table, saved)
            ui.notify('Preferences saved', color='positive')
            dialog.close()

        async def reset() -> None:
            await service.reset(actor, custom.key)
            apply_saved_config(table, None)
            ui.notify('Table reset to defaults', color='positive')
            dialog.close()

        with dialog_actions().classes('justify-end'):
            ui.button('Reset to defaults', on_click=reset).props('flat color=negative')
            ui.space()
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Confirm', on_click=confirm).props('color=primary')

    dialog.open()
