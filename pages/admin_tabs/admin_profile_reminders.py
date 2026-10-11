"""Admin Profile Reminders tab.

STAFF pick which profile items every member of this community should have done
(Challonge linked, pronouns set, ...). A member missing one sees a red banner on
every page until they do it or, where the rule allows, dismiss it. Reads and
writes go through :class:`ProfileNudgeService`.
"""

from nicegui import app, ui

from application.services import AuthService, ProfileNudgeService, get_user_from_discord_id
from application.services.profile_nudge_service import CHECKS, MAX_NOTE_LENGTH


async def admin_profile_reminders_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_edit = await AuthService.is_staff(actor)
    service = ProfileNudgeService()

    rules = {r['check']: r for r in await service.get_rules()}
    unavailable = await service.unavailable_reasons()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Profile reminders').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'Pick what every member of this community should have on their profile. '
            "Anyone who hasn't done it sees a red banner at the top of every page, "
            'with a button that takes them straight to the right spot on their profile. '
            'Leave everything unticked and nobody sees a banner.'
        ).classes('text-caption text-grey')

        controls: dict = {}
        for spec in CHECKS:
            rule = rules.get(spec.check)
            reason = unavailable.get(spec.check)
            with ui.card().classes('card-full-width'):
                enabled = ui.checkbox(spec.label, value=rule is not None).classes('text-weight-medium')
                ui.label(f'Banner: “{spec.prompt}”').classes('text-caption text-grey')
                if reason:
                    ui.label(f"{reason} Members won't see this one even if it's ticked.") \
                        .classes('text-caption text-warning')
                with ui.column().classes('w-full gap-1') as details:
                    dismissible = ui.switch(
                        'Members can dismiss it',
                        value=rule['dismissible'] if rule else True,
                    )
                    ui.label(
                        'Off means the banner stays until they actually do it.'
                    ).classes('text-caption text-grey')
                    note = ui.input(
                        'Note on the banner (optional)',
                        value=(rule or {}).get('note') or '',
                        placeholder='e.g. Required for the Season 4 bracket.',
                        validation={f'Keep it under {MAX_NOTE_LENGTH} characters':
                                    lambda v: len(v or '') <= MAX_NOTE_LENGTH},
                    ).props('outlined dense stack-label').classes('input-full-width')
                details.bind_visibility_from(enabled, 'value')
                controls[spec.check] = (enabled, dismissible, note)
                if not can_edit:
                    enabled.disable()
                    dismissible.disable()
                    note.disable()

        if actor is None or not can_edit:
            ui.label('Only Staff can change this.').classes('text-caption text-grey')
            return

        async def save() -> None:
            payload = [
                {'check': check.value, 'dismissible': dismissible.value, 'note': note.value}
                for check, (enabled, dismissible, note) in controls.items()
                if enabled.value
            ]
            try:
                await service.set_rules(actor, payload)
            except ValueError as e:
                ui.notify(str(e), color='warning')
                return
            except PermissionError as e:
                ui.notify(str(e), color='negative')
                return
            ui.notify('Profile reminders saved', color='positive')

        with ui.row().classes('gap-2 mt-2'):
            ui.button('Save', icon='save', on_click=save).props('color=primary')
