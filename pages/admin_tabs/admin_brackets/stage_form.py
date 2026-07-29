"""Create / edit / delete one bracket stage.

One form serves both create and edit: a DRAFT stage has no match graph, so every
field on it — including the format — is still safe to change, and the same dialog
that authored it can correct it.
"""

from typing import Dict

from nicegui import ui

from application.tenant_context import tenant_scope
from models import BracketFormat
from theme.brackets import FORMAT_OPTIONS
from theme.dialog._helpers import dialog_actions, form_dialog, submit_on_enter
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.notify import notify_error
from theme.tables.admin_crud import current_actor

# Config keys this form owns. Anything else in the blob — notably the per-round
# best-of / scheduled-time metadata the manage dialog writes — is carried through
# an edit untouched rather than being replaced by whatever the form happens to
# hold.
_FORM_CONFIG_KEYS = ('swiss_rounds', 'group_count', 'advancement')


async def open_stage_form(
    client,
    *,
    service,
    tenant_id,
    tournament_id,
    row=None,
    default_stage_order: int = 0,
    on_change,
) -> None:
    """Open the create dialog, or the edit dialog when ``row`` is given."""
    is_edit = row is not None
    with client:
        bracket = None
        if is_edit:
            with tenant_scope(tenant_id):
                bracket = await service.get_bracket(row['id'])
            if bracket is None:
                notify_error(ValueError('Bracket not found.'))
                return
        config = dict(bracket.config or {}) if bracket else {}
        advancement = config.get('advancement') or {}

        title = f'Edit stage — {bracket.name}' if is_edit else 'Create bracket stage'
        with form_dialog(title) as dialog:
            name_in = ui.input('Name', value=bracket.name if bracket else '').classes('w-full')
            fmt_in = ui.select(
                FORMAT_OPTIONS,
                value=bracket.format.value if bracket else BracketFormat.SINGLE_ELIM.value,
                label='Format',
            ).classes('w-full')
            stage_in = ui.number(
                'Stage order (0 = first stage)',
                value=bracket.stage_order if bracket else default_stage_order,
                min=0, precision=0,
            ).props('inputmode=numeric').classes('w-full')

            with ui.expansion('Format / advancement options').classes('w-full'):
                swiss_in = ui.number(
                    'Swiss rounds (optional)', value=config.get('swiss_rounds'),
                    min=1, precision=0,
                ).props('inputmode=numeric').classes('w-full')
                groups_in = ui.number(
                    'Round-robin group count (optional)', value=config.get('group_count'),
                    min=1, precision=0,
                ).props('inputmode=numeric').classes('w-full')
                ui.label('Advancement (stage > 0 only)').classes('text-caption text-grey')
                adv_count_in = ui.number(
                    'Advance count (optional)', value=advancement.get('count'),
                    min=1, precision=0,
                ).props('inputmode=numeric').classes('w-full')
                adv_per_group_in = ui.switch(
                    'Per group', value=bool(advancement.get('per_group', False)),
                )
                adv_seeding_in = ui.select(
                    {'snake': 'Snake', 'preserve': 'Preserve'},
                    value=advancement.get('seeding', 'snake'), label='Seeding',
                ).classes('w-full')

            async def submit() -> None:
                new_config: Dict[str, object] = {
                    k: v for k, v in config.items() if k not in _FORM_CONFIG_KEYS
                }
                if swiss_in.value:
                    new_config['swiss_rounds'] = int(swiss_in.value)
                if groups_in.value:
                    new_config['group_count'] = int(groups_in.value)
                if adv_count_in.value:
                    new_config['advancement'] = {
                        'count': int(adv_count_in.value),
                        'per_group': adv_per_group_in.value,
                        'seeding': adv_seeding_in.value,
                    }
                with tenant_scope(tenant_id):
                    actor = await current_actor()
                    try:
                        if is_edit:
                            await service.update_bracket(
                                actor, bracket.id,
                                name=name_in.value or '',
                                stage_order=int(stage_in.value or 0),
                                # A dict, never None: None means "leave the blob
                                # alone", which would make clearing the
                                # advancement rule impossible from this form.
                                config=new_config,
                                format=fmt_in.value,
                            )
                        else:
                            await service.create_bracket(
                                actor, tournament_id, name_in.value or '', fmt_in.value,
                                int(stage_in.value or 0), new_config or None,
                            )
                    except (ValueError, PermissionError) as ex:
                        notify_error(ex)
                        return
                ui.notify('Stage saved' if is_edit else 'Bracket created', color='positive')
                dialog.close()
                await on_change()

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button(
                    'Save' if is_edit else 'Create',
                    icon='save' if is_edit else 'add', on_click=submit,
                ).props('color=primary')
            submit_on_enter(dialog, submit)
        dialog.open()


async def confirm_delete_stage(row, client, *, service, tenant_id, on_change) -> None:
    """Delete a DRAFT stage, after asking."""
    with client:
        async def do_delete() -> None:
            confirm.dialog.close()
            actor = await current_actor()
            with tenant_scope(tenant_id):
                try:
                    await service.delete_bracket(actor, row['id'])
                except (ValueError, PermissionError) as ex:
                    notify_error(ex)
                    return
            ui.notify('Stage deleted', color='positive')
            await on_change()

        confirm = ConfirmationDialog(
            f"Delete “{row['name']}”? Its enrollments and seeding go with it. The "
            'tournament roster is untouched — entrants belong to the tournament, '
            'not to this stage.',
            on_confirm=do_delete,
            confirm_text='Delete stage',
        )
        confirm.open()
