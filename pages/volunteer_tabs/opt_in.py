"""Volunteer Opt-in / Status tab."""

from nicegui import ui

from application.services import current_user_from_storage
from application.services.volunteer_profile_service import VolunteerProfileService


async def opt_in_tab() -> None:
    user = await current_user_from_storage()
    if user is None:
        ui.label('You must be logged in.').classes('text-error')
        return

    service = VolunteerProfileService()

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('Volunteering at SGLive').classes('page-title')
        ui.separator().classes('separator-spacing')

        @ui.refreshable
        async def status_card() -> None:
            profile = await service.get_or_create(user)
            opted_in = profile.opted_in_at is not None

            with ui.card().classes('full-width q-pa-md'):
                if opted_in:
                    ui.label('✅ You are opted in to volunteer.').classes('text-h6')
                    ui.label(
                        'Coordinators can now schedule you. Set your availability so they '
                        'know when you can work.'
                    ).classes('text-body2')
                else:
                    ui.label('You have not opted in yet.').classes('text-h6')
                    ui.label(
                        'Opt in to let the coordinators schedule you for shifts at the event.'
                    ).classes('text-body2')

                note_input = ui.textarea(
                    'Arrival / departure notes (optional)',
                    value=profile.note or '',
                ).classes('full-width').props('autogrow')

                async def do_opt_in() -> None:
                    try:
                        await service.opt_in(user, note=note_input.value or None)
                        ui.notify('You are opted in. Thanks for volunteering!', color='positive')
                    except (ValueError, PermissionError) as e:
                        ui.notify(str(e), color='warning')
                        return
                    status_card.refresh()

                async def do_opt_out() -> None:
                    await service.opt_out(user)
                    ui.notify('You have opted out.', color='info')
                    status_card.refresh()

                async def save_note() -> None:
                    await service.update_note(user, note_input.value or None)
                    ui.notify('Notes saved.', color='positive')

                with ui.row().classes('q-mt-sm'):
                    if opted_in:
                        ui.button('Save notes', icon='save', on_click=save_note).props('color=primary')
                        ui.button('Opt out', icon='logout', on_click=do_opt_out).props('flat color=negative')
                    else:
                        ui.button('Opt in to volunteer', icon='how_to_reg', on_click=do_opt_in).props('color=primary')

        await status_card()
