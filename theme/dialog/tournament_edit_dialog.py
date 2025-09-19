from nicegui import ui
from models import Tournament

import asyncio

class TournamentDialog:
    def __init__(self, tournament=None, on_submit=None):
        self.tournament = tournament
        self.on_submit = on_submit
        self.dialog = None

    async def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            name_input = ui.input('Tournament Name', value=self.tournament.name if self.tournament else '')
            description_input = ui.textarea('Description', value=self.tournament.description if self.tournament and self.tournament.description else '').style('width: 100')
            seed_generator_input = ui.input('Seed Generator', value=self.tournament.seed_generator if self.tournament and self.tournament.seed_generator else '')
            with ui.row():
                players_per_match_input = ui.number('Players per Match', value=self.tournament.players_per_match if self.tournament else 2, min=1, max=100)
                team_size_input = ui.number('Team Size', value=self.tournament.team_size if self.tournament else 1, min=1, max=100)
            staff_administered_checkbox = ui.checkbox('Staff Administered', value=self.tournament.staff_administered if self.tournament else False)
            is_active_checkbox = ui.checkbox('Active', value=self.tournament.is_active if self.tournament else True)

            async def submit():
                if self.tournament:
                    with self.dialog:
                        self.tournament.name = name_input.value
                        self.tournament.description = description_input.value
                        self.tournament.seed_generator = seed_generator_input.value
                        self.tournament.is_active = is_active_checkbox.value
                        self.tournament.players_per_match = players_per_match_input.value
                        self.tournament.team_size = team_size_input.value
                        self.tournament.staff_administered = staff_administered_checkbox.value
                        await self.tournament.save()
                        ui.notify('Tournament updated.', color='positive')
                        dialog.close()
                        if self.on_submit:
                            await self.on_submit(self.tournament)
                else:
                    name = name_input.value.strip()
                    description = description_input.value.strip()
                    seed_generator = seed_generator_input.value.strip()
                    is_active = is_active_checkbox.value
                    players_per_match = players_per_match_input.value
                    team_size = team_size_input.value
                    staff_administered = staff_administered_checkbox.value
                    if not name:
                        with self.dialog:
                            ui.notify('Tournament name is required.', color='warning')
                        return
                    new_tournament = await Tournament.create(
                        name=name,
                        description=description,
                        seed_generator=seed_generator,
                        is_active=is_active,
                        players_per_match=players_per_match,
                        team_size=team_size,
                        staff_administered=staff_administered
                    )
                    with self.dialog:
                        ui.notify('Tournament created.', color='positive')
                        dialog.close()
                        if self.on_submit:
                            await self.on_submit(new_tournament)

            with ui.row().classes('justify-between').style('margin-top: 1em;'):
                if self.tournament:
                    ui.button('Save', color='green', on_click=submit)
                else:
                    ui.button('Create', color='green', on_click=submit)
                ui.button('Cancel', color='gray', on_click=dialog.close)
            def on_keydown(e):
                if e.args and e.args.get('key') == 'Enter':
                    asyncio.create_task(submit())
            dialog.on('keydown', on_keydown)
            dialog.open()
