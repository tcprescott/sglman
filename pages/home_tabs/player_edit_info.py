"""Player Edit Info Tab - Allows players to edit their personal information and tournament registrations."""

import asyncio

from nicegui import app, ui

from application.services import ChallongeService, TournamentNotificationService, UserService
from models import User
from pages.home_tabs.api_tokens_section import render_api_tokens_section
from pages.home_tabs.challonge_link_section import render_challonge_link_section


async def render_edit_info_tab():
    """Render the edit info tab for players to update their information."""
    # Initialize service
    user_service = UserService()

    # Install a beforeunload guard so unsaved edits prompt before navigation.
    ui.add_head_html("""
    <script>
      if (!window.__sglman_dirty_guard_installed) {
        window.__sglman_dirty_guard_installed = true;
        window.sglman_dirty = false;
        window.addEventListener('beforeunload', (e) => {
          if (window.sglman_dirty) {
            e.preventDefault();
            e.returnValue = '';
          }
        });
      }
    </script>
    """)

    def mark_dirty():
        ui.run_javascript('window.sglman_dirty = true;')

    def mark_clean():
        ui.run_javascript('window.sglman_dirty = false;')

    # Subtle auto-save status indicator (elements created near the end of the form).
    status_icon = None
    status_label = None

    def show_saving():
        status_icon.props('name=sync').classes(replace='text-muted')
        status_label.set_text('Saving…')
        status_label.classes(replace='text-muted')

    def show_saved():
        status_icon.props('name=check').classes(replace='text-muted')
        status_label.set_text('Saved')
        status_label.classes(replace='text-muted')

    def show_error(message):
        status_icon.props('name=error').classes(replace='text-warning')
        status_label.set_text(message)
        status_label.classes(replace='text-warning')

    with ui.column().classes('page-container-narrow'):
        # Header
        with ui.row().classes('header-row'):
            ui.label('Edit Your Information').classes('page-title')
        
        ui.separator().classes('separator-spacing')
        
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            with ui.card().classes('card-centered'):
                ui.icon('lock', size='3em').classes('icon-large')
                ui.label('You must be logged in to view this page.').classes('text-muted')
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary size=lg')
            return
        
        user = await User.get_or_none(discord_id=discord_id)
        if user is None:
            with ui.card().classes('card-centered'):
                ui.icon('error', size='3em').classes('icon-error')
                ui.label('User not found in the database.').classes('text-italic')
            return

        # Get tournaments and user registrations from service
        tournament_data = await user_service.get_active_tournaments_categorized()
        user_tournaments = await user_service.get_user_tournament_registrations(user)
        
        tournaments = tournament_data['all_tournaments']
        staff_tournaments = tournament_data['staff_tournaments']
        player_tournaments = tournament_data['player_tournaments']
        selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]

        # Challonge-linked tournaments handle participation automatically via the
        # bracket mirror, so their opt-in checkbox is read-only and reflects
        # bracket membership rather than a manual choice.
        challonge_service = ChallongeService()
        account_linked = bool(user.challonge_user_id)
        challonge_participant_ids = await challonge_service.participant_tournament_ids(user)
        # Existing manual enrollments for linked tournaments must be preserved
        # untouched when the player edits their other (manual) selections.
        challonge_enrolled_ids = {
            t.id for t in tournaments if t.challonge_tournament_id and t.id in selected_tournament_ids
        }

        # Per-tournament match notification preferences
        notification_service = TournamentNotificationService()
        active_tournaments = await notification_service.get_active_tournaments()
        existing_prefs = await notification_service.get_user_preferences(user)
        prefs_by_tournament = {p.tournament_id: p for p in existing_prefs}

        level_options = {
            'none': 'None',
            'streamed': 'Streamed only',
            'streamed_and_candidates': 'Streamed & Candidates',
            'all': 'All matches',
        }
        pref_widgets = {}

        personal_token = {'n': 0}

        async def on_personal_change():
            mark_dirty()
            personal_token['n'] += 1
            mine = personal_token['n']
            await asyncio.sleep(0.8)
            if mine != personal_token['n']:
                return
            show_saving()
            try:
                await user_service.update_user_personal_info(
                    user=user,
                    actor=user,
                    display_name=display_name_input.value,
                    pronouns=pronouns_input.value,
                    dm_notifications=dm_checkbox.value,
                )
            except ValueError as e:
                show_error(str(e))
                ui.notify(str(e), color='warning')
                return
            show_saved()
            mark_clean()

        async def on_tournament_change():
            mark_dirty()
            selected_ids = set(tid for tid, cb in tournament_checkboxes.items() if cb.value)
            # Challonge-managed enrollments aren't editable here; carry them
            # through so the full-set update doesn't drop them.
            selected_ids |= challonge_enrolled_ids
            show_saving()
            try:
                await user_service.manage_tournament_enrollments(
                    user=user,
                    actor=user,
                    tournament_ids=selected_ids,
                    is_update=True,
                )
            except ValueError as e:
                show_error(str(e))
                ui.notify(str(e), color='warning')
                return
            show_saved()
            mark_clean()

        async def on_notification_pref_change(tournament_id: int):
            mark_dirty()
            show_saving()
            try:
                await notification_service.upsert_preference(
                    user=user,
                    tournament_id=tournament_id,
                    match_notifications=pref_widgets[tournament_id].value,
                )
            except ValueError as e:
                show_error(str(e))
                ui.notify(str(e), color='warning')
                return
            show_saved()
            mark_clean()

        # Auto-save status indicator (updated by the on_change handlers above).
        with ui.row().classes('row-centered'):
            status_icon = ui.icon('check', size='xs').classes('text-muted')
            status_label = ui.label('All changes are saved automatically').classes('text-muted')

        # Personal Information Section
        with ui.card().classes('card-full-width'):
            ui.label('Personal Information').classes('section-title')
            
            with ui.grid(columns=2).classes('form-grid'):
                display_name_hint = f"Default: {user.username}" if not user.display_name else ""
                with ui.column():
                    ui.label('Display Name').classes('input-label')
                    display_name_input = ui.input(
                        '',
                        value=user.display_name or '',
                        placeholder=display_name_hint,
                        on_change=on_personal_change,
                    ).classes('input-full-width').props('outlined dense')

                with ui.column():
                    ui.label('Pronouns').classes('input-label')
                    pronouns_input = ui.input(
                        '',
                        value=user.pronouns or '',
                        placeholder='e.g. they/them',
                        on_change=on_personal_change,
                    ).classes('input-full-width').props('outlined dense')

        with ui.card().classes('card-full-width'):
            ui.label('Notifications').classes('section-title')
            dm_checkbox = ui.checkbox(
                'Receive Discord DM notifications for match updates',
                value=user.dm_notifications,
                on_change=on_personal_change,
            )

            ui.separator().classes('separator-spacing')
            ui.label('Match Notification Preferences').classes('input-label')
            ui.label(
                'Choose when to receive Discord DMs about scheduled matches. '
                '"Streamed & Candidates" also alerts you when a match may be streamed.'
            ).classes('text-caption text-grey-7')

            if not active_tournaments:
                ui.label('No active tournaments.').classes('text-muted')
            else:
                for tournament in active_tournaments:
                    existing = prefs_by_tournament.get(tournament.id)
                    current_level = existing.match_notifications if existing else 'none'
                    with ui.row().classes('items-center full-width q-my-xs'):
                        ui.label(tournament.name).classes('col-grow')
                        pref_widgets[tournament.id] = ui.select(
                            options=level_options,
                            value=current_level,
                            on_change=lambda _, tid=tournament.id: on_notification_pref_change(tid),
                        ).classes('col-auto').style('min-width: 200px')

        tournament_checkboxes = {}
        staff_tournaments = [t for t in tournaments if t.staff_administered]
        player_tournaments = [t for t in tournaments if not t.staff_administered]

        def render_tournament_grid(tournament_list, label, icon, columns=4):
            if not tournament_list:
                return
                
            with ui.card().classes('card-full-width'):
                with ui.row().classes('row-centered'):
                    ui.icon(icon, size='sm').classes('icon-primary')
                    ui.label(label).classes('section-title')
                
                rows = [tournament_list[i:i+columns] for i in range(0, len(tournament_list), columns)]
                for row in rows:
                    with ui.row().classes('row-spacing'):
                        for t in row:
                            with ui.column().classes('flex-1'):
                                if t.challonge_tournament_id:
                                    render_challonge_tournament(t)
                                else:
                                    tournament_checkboxes[t.id] = ui.checkbox(
                                        t.name,
                                        value=t.id in selected_tournament_ids,
                                        on_change=on_tournament_change,
                                    ).classes('input-full-width')
                        # Fill empty cells if less than columns
                        for _ in range(columns - len(row)):
                            ui.column().classes('flex-1')

        def render_challonge_tournament(t):
            """Read-only opt-in for a Challonge-linked tournament.

            Participation is driven by the synced bracket, so the checkbox is
            disabled and just reflects bracket membership. Players who haven't
            linked their Challonge account get a call to action to do so.
            """
            in_bracket = t.id in challonge_participant_ids
            checkbox = ui.checkbox(t.name, value=in_bracket).classes('input-full-width')
            checkbox.props('disable')
            checkbox.tooltip('Enrollment for this tournament is managed automatically through Challonge.')
            if t.challonge_tournament_url:
                ui.link('View bracket', t.challonge_tournament_url, new_tab=True).classes('text-caption')
            if account_linked:
                ui.label('Enrollment managed automatically via Challonge.').classes(
                    'text-caption text-grey-7'
                )
            else:
                ui.label('Link your Challonge account to be enrolled automatically.').classes(
                    'text-caption text-grey-7'
                )
                ui.button(
                    'Link Challonge account', icon='link',
                    on_click=lambda: ui.navigate.to('/challonge/link'),
                ).props('flat dense color=primary size=sm')

        # Tournament Sections
        render_tournament_grid(staff_tournaments, 'Staff Administered Tournaments', 'emoji_events', columns=1)
        render_tournament_grid(player_tournaments, 'Community Tournaments', 'groups', columns=1)

        # Challonge account linking (self-contained)
        await render_challonge_link_section(user)

        # API token management (self-contained; saves independently of the form above)
        await render_api_tokens_section(user)
