import asyncio

from nicegui import ui

from application.services import SeedGenerationService, TournamentService

class TournamentDialog:
    def __init__(self, tournament=None, on_submit=None):
        self.tournament = tournament
        self.on_submit = on_submit
        self.dialog = None
        self.tournament_service = TournamentService()

    async def open(self):
        with ui.dialog() as dialog, ui.card():
            self.dialog = dialog
            name_input = ui.input('Tournament Name', value=self.tournament.name if self.tournament else '')
            description_input = ui.textarea('Description', value=self.tournament.description if self.tournament and self.tournament.description else '').style('width: 100')
            randomizer_choices = ['None'] + SeedGenerationService.AVAILABLE_RANDOMIZERS
            default_seed = self.tournament.seed_generator if self.tournament and self.tournament.seed_generator else None
            seed_generator_input = ui.select(randomizer_choices, label='Seed Generator', value=default_seed)
            bracket_url_input = ui.input('Bracket URL', value=self.tournament.bracket_url if self.tournament and self.tournament.bracket_url else '')
            rules_url_input = ui.input('Rules URL', value=self.tournament.rules_url if self.tournament and self.tournament.rules_url else '')
            tournament_format_input = ui.input('Tournament Format', value=self.tournament.tournament_format if self.tournament and self.tournament.tournament_format else '')
            average_match_duration_input = ui.number('Average Match Duration (min)', value=self.tournament.average_match_duration if self.tournament and self.tournament.average_match_duration else None, min=0)
            max_match_duration_input = ui.number('Max Match Duration (min)', value=self.tournament.max_match_duration if self.tournament and self.tournament.max_match_duration else None, min=0)
            with ui.row():
                players_per_match_input = ui.number('Players per Match', value=self.tournament.players_per_match if self.tournament else 2, min=1, max=100)
                team_size_input = ui.number('Team Size', value=self.tournament.team_size if self.tournament else 1, min=1, max=100)
            with ui.row():
                staff_administered_checkbox = ui.checkbox('Staff Administered', value=self.tournament.staff_administered if self.tournament else False)
                is_active_checkbox = ui.checkbox('Active', value=self.tournament.is_active if self.tournament else True)

            async def submit():
                try:
                    if self.tournament:
                        with self.dialog:
                            await self.tournament_service.update_tournament(
                                self.tournament,
                                name=name_input.value,
                                description=description_input.value,
                                seed_generator=seed_generator_input.value,
                                bracket_url=bracket_url_input.value,
                                rules_url=rules_url_input.value,
                                tournament_format=tournament_format_input.value,
                                average_match_duration=average_match_duration_input.value,
                                max_match_duration=max_match_duration_input.value,
                                is_active=is_active_checkbox.value,
                                players_per_match=players_per_match_input.value,
                                team_size=team_size_input.value,
                                staff_administered=staff_administered_checkbox.value
                            )
                            ui.notify('Tournament updated.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(self.tournament)
                    else:
                        new_tournament = await self.tournament_service.create_tournament(
                            name=name_input.value,
                            description=description_input.value,
                            seed_generator=seed_generator_input.value,
                            bracket_url=bracket_url_input.value,
                            rules_url=rules_url_input.value,
                            tournament_format=tournament_format_input.value,
                            average_match_duration=average_match_duration_input.value,
                            max_match_duration=max_match_duration_input.value,
                            is_active=is_active_checkbox.value,
                            players_per_match=players_per_match_input.value,
                            team_size=team_size_input.value,
                            staff_administered=staff_administered_checkbox.value
                        )
                        with self.dialog:
                            ui.notify('Tournament created.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(new_tournament)
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error: {str(e)}', color='negative')

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
