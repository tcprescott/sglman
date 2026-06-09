from nicegui import background_tasks, ui

from application.services import TournamentNotificationService
from models import User


class TournamentNotificationDialog:
    """Dialog for managing per-tournament match notification preferences."""

    def __init__(self, user: User, on_close=None):
        self.user = user
        self.on_close = on_close
        self.notification_service = TournamentNotificationService()

    async def open(self):
        active_tournaments = await self.notification_service.get_active_tournaments()
        existing_prefs = await self.notification_service.get_user_preferences(self.user)
        prefs_by_tournament = {p.tournament_id: p for p in existing_prefs}

        level_options = {
            'none': 'None',
            'streamed': 'Streamed only',
            'streamed_and_candidates': 'Streamed & Candidates',
            'all': 'All matches',
        }

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            with ui.row().classes('items-center q-pa-sm'):
                ui.label('Match Notification Preferences').classes('text-h6 q-ma-none')
                ui.space()
                ui.button(icon='close', on_click=dialog.close).props('flat round dense').tooltip('Close')
            ui.separator()
            with ui.column().classes('q-pa-md gap-2'):
                ui.label(
                    'Choose when to receive Discord DMs about scheduled matches. '
                    '"Streamed & Candidates" also alerts you when a match may be streamed.'
                ).classes('text-caption text-grey-7')

                pref_widgets: dict = {}

                if not active_tournaments:
                    ui.label('No active tournaments.').classes('text-grey-7')
                else:
                    for tournament in active_tournaments:
                        existing = prefs_by_tournament.get(tournament.id)
                        current_level = existing.match_notifications if existing else 'none'
                        with ui.row().classes('items-center full-width q-my-xs'):
                            ui.label(tournament.name).classes('col-grow')
                            level_select = ui.select(
                                options=level_options,
                                value=current_level,
                            ).classes('col-auto').style('min-width: 200px')
                            pref_widgets[tournament.id] = level_select

            async def save():
                try:
                    for tournament in active_tournaments:
                        await self.notification_service.upsert_preference(
                            user=self.user,
                            tournament_id=tournament.id,
                            match_notifications=pref_widgets[tournament.id].value,
                        )
                    with dialog:
                        ui.notify('Notification preferences saved.', color='positive')
                    dialog.close()
                    if self.on_close:
                        await self.on_close()
                except ValueError as e:
                    with dialog:
                        ui.notify(str(e), color='warning')

            ui.separator()
            with ui.row().classes('justify-end q-pa-sm gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=lambda: background_tasks.create(save())).props('color=primary')

            dialog.open()
