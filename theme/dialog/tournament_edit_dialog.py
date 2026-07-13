from nicegui import app, ui

from application.services import (
    ChallongeService,
    PresetService,
    SeedGenerationService,
    TournamentService,
    get_user_from_discord_id,
)
from theme.dialog._helpers import dialog_actions, dialog_header, mobile_sheet, submit_on_enter


class TournamentDialog:
    def __init__(self, tournament=None, on_submit=None):
        self.tournament = tournament
        self.on_submit = on_submit
        self.dialog = None
        self.tournament_service = TournamentService()
        self.challonge_service = ChallongeService()
        self.preset_service = PresetService()

    async def open(self):
        is_create = self.tournament is None
        title = 'Add Tournament' if is_create else 'Edit Tournament'

        with ui.dialog() as dialog, ui.card().classes('dialog-card'):
            self.dialog = dialog
            mobile_sheet(dialog)
            dialog_header(title, dialog)
            with ui.column().classes('q-pa-md gap-2'):
                ui.label('* required').classes('required-legend')
                name_input = ui.input(
                    'Tournament Name *',
                    value=self.tournament.name if self.tournament else '',
                ).props('required').classes('input-full-width')
                description_input = ui.textarea(
                    'Description',
                    value=self.tournament.description if self.tournament and self.tournament.description else '',
                ).classes('input-full-width')
                randomizer_choices = ['None'] + SeedGenerationService.AVAILABLE_RANDOMIZERS
                default_seed = self.tournament.seed_generator if self.tournament and self.tournament.seed_generator else None
                seed_generator_input = ui.select(
                    randomizer_choices, label='Seed Generator', value=default_seed,
                ).classes('input-full-width')
                presets = await self.preset_service.list_selectable()
                # None (0) clears the FK; ui.select cannot key an option on None,
                # so a 0 sentinel stands in and maps back to None on submit.
                preset_options = {0: '— None (use Seed Generator) —'}
                preset_options.update({p.id: f'{p.randomizer} / {p.name}' for p in presets})
                default_preset = self.tournament.preset_id if self.tournament and self.tournament.preset_id else 0
                preset_input = ui.select(
                    preset_options, label='Seed Preset', value=default_preset,
                ).classes('input-full-width').props(
                    'hint="Overrides Seed Generator when set — resolves the preset\'s randomizer & settings."'
                )
                bracket_url_input = ui.input(
                    'Bracket URL',
                    value=self.tournament.bracket_url if self.tournament and self.tournament.bracket_url else '',
                ).classes('input-full-width')
                rules_url_input = ui.input(
                    'Rules URL',
                    value=self.tournament.rules_url if self.tournament and self.tournament.rules_url else '',
                ).classes('input-full-width')
                tournament_format_input = ui.input(
                    'Tournament Format',
                    value=self.tournament.tournament_format if self.tournament and self.tournament.tournament_format else '',
                ).classes('input-full-width')
                triforce_access_message_input = ui.textarea(
                    'Triforce Text Access Message',
                    value=self.tournament.triforce_access_message if self.tournament and self.tournament.triforce_access_message else '',
                ).classes('input-full-width').props(
                    'hint="Shown (as markdown) to users without submit access — e.g. how to purchase it."'
                )
                with ui.row().classes('gap-2'):
                    average_match_duration_input = ui.number(
                        'Avg Match Duration (min)',
                        value=self.tournament.average_match_duration if self.tournament and self.tournament.average_match_duration else None,
                        min=0,
                    ).props('inputmode=numeric')
                    max_match_duration_input = ui.number(
                        'Max Match Duration (min)',
                        value=self.tournament.max_match_duration if self.tournament and self.tournament.max_match_duration else None,
                        min=0,
                    ).props('inputmode=numeric')
                with ui.row().classes('gap-2'):
                    players_per_match_input = ui.number(
                        'Players per Match',
                        value=self.tournament.players_per_match if self.tournament else 2,
                        min=1, max=100,
                    ).props('inputmode=numeric')
                    team_size_input = ui.number(
                        'Team Size',
                        value=self.tournament.team_size if self.tournament else 1,
                        min=1, max=100,
                    ).props('inputmode=numeric')
                with ui.row().classes('gap-4'):
                    staff_administered_checkbox = ui.checkbox(
                        'Staff Administered',
                        value=self.tournament.staff_administered if self.tournament else False,
                    )
                    is_active_checkbox = ui.checkbox(
                        'Active',
                        value=self.tournament.is_active if self.tournament else True,
                    )

                if self.tournament and self.challonge_service.is_configured():
                    ui.separator()
                    ui.label('Challonge').classes('text-bold')
                    challonge_status = ui.label().classes('text-caption text-muted')

                    def render_challonge_status() -> None:
                        if self.tournament.challonge_tournament_id:
                            challonge_status.set_text(
                                f"Linked to Challonge tournament {self.tournament.challonge_tournament_id}"
                            )
                        else:
                            challonge_status.set_text('Not linked to a Challonge tournament.')

                    render_challonge_status()
                    challonge_input = ui.input(
                        'Challonge tournament ID or URL',
                        value=self.tournament.challonge_tournament_url or self.tournament.challonge_tournament_id or '',
                    ).classes('input-full-width')

                    async def link_and_sync() -> None:
                        value = (challonge_input.value or '').strip()
                        if not value:
                            with self.dialog:
                                ui.notify('Enter a Challonge tournament ID or URL.', color='warning')
                            return
                        try:
                            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                            await self.challonge_service.link_tournament(self.tournament.id, value, actor)
                            await self.tournament.refresh_from_db()
                            with self.dialog:
                                ui.notify('Linked and synced with Challonge.', color='positive')
                                render_challonge_status()
                        except ValueError as e:
                            with self.dialog:
                                ui.notify(str(e), color='warning')
                        except Exception as e:  # noqa: BLE001
                            with self.dialog:
                                ui.notify(f'Challonge link failed: {e}', color='negative')

                    ui.button('Link & Sync', icon='sync', on_click=link_and_sync).props('flat color=primary')

            async def submit():
                if not (name_input.value or '').strip():
                    with self.dialog:
                        ui.notify('Please fill required field(s): Tournament Name.', color='warning')
                    return
                try:
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
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
                                triforce_access_message=triforce_access_message_input.value,
                                average_match_duration=average_match_duration_input.value,
                                max_match_duration=max_match_duration_input.value,
                                is_active=is_active_checkbox.value,
                                players_per_match=players_per_match_input.value,
                                team_size=team_size_input.value,
                                staff_administered=staff_administered_checkbox.value,
                                preset_id=(preset_input.value or None),
                                actor=actor,
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
                            triforce_access_message=triforce_access_message_input.value,
                            average_match_duration=average_match_duration_input.value,
                            max_match_duration=max_match_duration_input.value,
                            is_active=is_active_checkbox.value,
                            players_per_match=players_per_match_input.value,
                            team_size=team_size_input.value,
                            staff_administered=staff_administered_checkbox.value,
                            preset_id=(preset_input.value or None),
                            actor=actor,
                        )
                        with self.dialog:
                            ui.notify('Tournament created.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(new_tournament)
                except PermissionError as e:
                    with self.dialog:
                        ui.notify(str(e), color='negative')
                except ValueError as e:
                    with self.dialog:
                        ui.notify(f'Error: {str(e)}', color='negative')

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                primary_btn = ui.button(
                    'Create' if is_create else 'Save', on_click=submit
                ).props('color=primary')
                primary_btn.bind_enabled_from(
                    name_input, 'value',
                    backward=lambda v: bool(v and v.strip()),
                )

            submit_on_enter(dialog, submit)
            dialog.open()
