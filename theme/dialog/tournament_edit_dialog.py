from datetime import date, timedelta

from nicegui import app, ui

from application.services import (
    AuthService,
    ChallongeService,
    FeatureFlagService,
    PresetService,
    RaceRoomProfileService,
    RacetimeBotService,
    SeedGenerationService,
    TournamentService,
    get_user_from_discord_id,
)
from application.tenant_context import require_tenant_id
from theme.dialog._helpers import (
    dialog_actions,
    dialog_header,
    mobile_sheet,
    native_date_input,
    native_time_input,
    submit_on_enter,
)
from theme.notify import notify_error


class TournamentDialog:
    def __init__(self, tournament=None, on_submit=None):
        self.tournament = tournament
        self.on_submit = on_submit
        self.dialog = None
        self.tournament_service = TournamentService()
        self.challonge_service = ChallongeService()
        self.preset_service = PresetService()
        self.racetime_bot_service = RacetimeBotService()
        self.race_room_profile_service = RaceRoomProfileService()

    async def open(self):
        is_create = self.tournament is None
        title = 'Add Tournament' if is_create else 'Edit Tournament'
        actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        can_sync = await AuthService.can_manage_sync(actor)
        # Racetime room automation is only offered to sync managers, and only the
        # bot categories this tenant is authorized for are selectable.
        rt = {}
        if can_sync:
            rt['bots'] = await self.racetime_bot_service.list_authorized_for_tenant(require_tenant_id())
            rt['profiles'] = await self.race_room_profile_service.list_selectable()

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
                default_seed = self.tournament.seed_generator if self.tournament and self.tournament.seed_generator else None
                live_flags = await FeatureFlagService().enabled_flags()
                seed_choices = SeedGenerationService.available_randomizers(live_flags)
                # Keep a previously-chosen (now flag-gated) generator selectable so
                # editing an existing tournament never silently drops its value.
                if default_seed and default_seed not in seed_choices:
                    seed_choices = seed_choices + [default_seed]
                randomizer_choices = ['None'] + seed_choices
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

                # --- Tournament Days (per-tournament override of the tenant setting) ---
                ui.separator()
                ui.label('Tournament Days').classes('text-bold')
                ui.label(
                    'Override the community event window and per-day match hours for '
                    'this tournament. Leave blank to use the community default.'
                ).classes('text-caption text-grey')

                t = self.tournament
                event_start_input = native_date_input(
                    'Event Start Date',
                    t.event_start_date.isoformat() if t and t.event_start_date else '',
                    clearable=True,
                )
                event_end_input = native_date_input(
                    'Event End Date',
                    t.event_end_date.isoformat() if t and t.event_end_date else '',
                    clearable=True,
                )

                # Stored blob seeds the grid; snapshotted on every refresh so
                # typed-but-unsaved values survive a date-window change.
                hours_state: dict = dict(t.tournament_hours) if t and t.tournament_hours else {}
                hours_inputs: dict[str, dict] = {}

                @ui.refreshable
                def render_hours() -> None:
                    for d_iso, row in hours_inputs.items():
                        hours_state[d_iso] = {
                            'open': (row['open'].value or ''),
                            'close': (row['close'].value or ''),
                        }
                    hours_inputs.clear()
                    start_raw = (event_start_input.value or '').strip()
                    end_raw = (event_end_input.value or '').strip()
                    try:
                        start_d = date.fromisoformat(start_raw)
                        end_d = date.fromisoformat(end_raw)
                    except ValueError:
                        ui.label(
                            'Set start and end dates to configure per-day hours.'
                        ).classes('text-caption text-grey')
                        return
                    if end_d < start_d:
                        ui.label('End date is before start date.').classes('text-caption text-warning')
                        return
                    ui.label('Per-day match hours (blank = any time):').classes('text-caption q-mt-sm')
                    current = start_d
                    rendered = 0
                    while current <= end_d and rendered < 60:
                        window = hours_state.get(current.isoformat())
                        open_val = window.get('open', '') if isinstance(window, dict) else ''
                        close_val = window.get('close', '') if isinstance(window, dict) else ''
                        with ui.row().classes('items-center gap-3'):
                            ui.label(current.isoformat()).classes('w-28 text-mono')
                            open_i = native_time_input('Open', open_val)
                            close_i = native_time_input('Close', close_val)
                            hours_inputs[current.isoformat()] = {'open': open_i, 'close': close_i}
                        current += timedelta(days=1)
                        rendered += 1

                render_hours()
                event_start_input.on('update:model-value', lambda: render_hours.refresh())
                event_end_input.on('update:model-value', lambda: render_hours.refresh())

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
                        except (ValueError, PermissionError) as e:
                            with self.dialog:
                                notify_error(e)

                    ui.button('Link & Sync', icon='sync', on_click=link_and_sync).props('flat color=primary')

                if can_sync:
                    ui.separator()
                    ui.label('Racetime').classes('text-bold')
                    t = self.tournament
                    # 0 sentinel stands in for "no FK" — ui.select cannot key on None.
                    bot_options = {0: '— None —'}
                    bot_options.update({b.id: f'{b.category} ({b.name})' for b in rt['bots']})
                    default_bot = t.racetime_bot_id if t and t.racetime_bot_id else 0
                    rt['bot_input'] = ui.select(
                        bot_options, label='Racetime Bot', value=default_bot,
                    ).classes('input-full-width').props(
                        'hint="Only categories your community is authorized for appear here."'
                    )
                    profile_options = {0: '— None —'}
                    profile_options.update({p.id: p.name for p in rt['profiles']})
                    default_profile = t.race_room_profile_id if t and t.race_room_profile_id else 0
                    rt['profile_input'] = ui.select(
                        profile_options, label='Race Room Profile', value=default_profile,
                    ).classes('input-full-width')
                    rt['goal_input'] = ui.input(
                        'Default Goal',
                        value=(t.racetime_default_goal if t and t.racetime_default_goal else ''),
                    ).classes('input-full-width')
                    with ui.row().classes('gap-2'):
                        rt['open_before_input'] = ui.number(
                            'Open Room (min before)',
                            value=(t.room_open_minutes_before if t else 30),
                            min=0,
                        ).props('inputmode=numeric')
                    with ui.row().classes('gap-4'):
                        rt['auto_create_input'] = ui.checkbox(
                            'Auto-create rooms',
                            value=(t.racetime_auto_create_rooms if t else False),
                        )
                        rt['require_link_input'] = ui.checkbox(
                            'Require racetime link',
                            value=(t.require_racetime_link if t else False),
                        )

            async def submit():
                if not (name_input.value or '').strip():
                    with self.dialog:
                        ui.notify('Please fill required field(s): Tournament Name.', color='warning')
                    return
                # Per-tournament days override: blank dates inherit the tenant
                # setting; only fully-filled day rows become hour windows.
                event_start_value = (event_start_input.value or '').strip() or None
                event_end_value = (event_end_input.value or '').strip() or None
                hours_mapping: dict[date, tuple[str, str]] = {}
                for d_iso, row in hours_inputs.items():
                    open_str = (row['open'].value or '').strip()
                    close_str = (row['close'].value or '').strip()
                    if open_str and close_str:
                        hours_mapping[date.fromisoformat(d_iso)] = (open_str, close_str)
                days_kwargs = dict(
                    event_start_date=event_start_value,
                    event_end_date=event_end_value,
                    tournament_hours=hours_mapping or None,
                )

                rt_kwargs = {}
                if can_sync:
                    rt_kwargs = dict(
                        racetime_bot_id=(rt['bot_input'].value or None),
                        race_room_profile_id=(rt['profile_input'].value or None),
                        racetime_auto_create_rooms=rt['auto_create_input'].value,
                        room_open_minutes_before=int(rt['open_before_input'].value or 0),
                        require_racetime_link=rt['require_link_input'].value,
                        racetime_default_goal=rt['goal_input'].value,
                    )
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
                                **days_kwargs,
                                **rt_kwargs,
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
                            **days_kwargs,
                            **rt_kwargs,
                        )
                        with self.dialog:
                            ui.notify('Tournament created.', color='positive')
                            dialog.close()
                            if self.on_submit:
                                await self.on_submit(new_tournament)
                except (ValueError, PermissionError) as e:
                    with self.dialog:
                        notify_error(e)

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
