"""Profile tab - a player's personal info, notifications, enrollment, and links."""

import asyncio

from nicegui import app, ui

from application.services import (
    ChallongeService,
    TournamentNotificationService,
    UserService,
    get_user_from_discord_id,
)
from pages.home_tabs._link_section import render_connected_accounts_section
from pages.home_tabs.api_tokens_section import render_api_tokens_section
from pages.home_tabs.challonge_link_section import CONFIG as CHALLONGE_CONFIG
from pages.home_tabs.racetime_link_section import CONFIG as RACETIME_CONFIG
from pages.home_tabs.twitch_link_section import CONFIG as TWITCH_CONFIG
from pages.home_tabs.web_push_section import render_web_push_section


async def render_edit_info_tab():
    """Render the profile tab for players to update their information."""
    # Initialize service
    user_service = UserService()

    # Install a beforeunload guard so unsaved edits prompt before navigation.
    ui.add_head_html("""
    <script>
      if (!window.__wizzrobe_dirty_guard_installed) {
        window.__wizzrobe_dirty_guard_installed = true;
        window.wizzrobe_dirty = false;
        window.addEventListener('beforeunload', (e) => {
          if (window.wizzrobe_dirty) {
            e.preventDefault();
            e.returnValue = '';
          }
        });
      }
    </script>
    """)

    def mark_dirty():
        ui.run_javascript('window.wizzrobe_dirty = true;')

    def mark_clean():
        ui.run_javascript('window.wizzrobe_dirty = false;')

    # Subtle auto-save status indicator (elements created just below the header).
    status_icon = None
    status_label = None

    def show_saving():
        status_icon.props('name=sync').classes(replace='text-muted')
        status_label.set_text('Saving…')
        status_label.classes(replace='text-muted')

    def show_saved():
        status_icon.props('name=check_circle').classes(replace='text-positive')
        status_label.set_text('Saved')
        status_label.classes(replace='text-muted')
        # A toast so the confirmation is visible even when the top-of-form
        # indicator has scrolled out of view (the common case on a phone).
        ui.notify('Saved', color='positive', position='bottom', timeout=1200)

    def show_error(message):
        status_icon.props('name=error').classes(replace='text-warning')
        status_label.set_text(message)
        status_label.classes(replace='text-warning')

    with ui.column().classes('page-container-form gap-4'):
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            with ui.card().classes('card-centered'):
                ui.icon('lock', size='3em').classes('icon-large')
                ui.label('You must be logged in to view this page.').classes('text-muted')
                ui.button('Login with Discord', icon='login', on_click=lambda: ui.navigate.to('/login')).props('color=primary size=lg')
            return

        user = await get_user_from_discord_id(discord_id)
        if user is None:
            with ui.card().classes('card-centered'):
                ui.icon('error', size='3em').classes('icon-error')
                ui.label('User not found in the database.').classes('text-italic')
            return

        # Get tournaments and user registrations from service
        tournament_data = await user_service.get_active_tournaments_categorized()
        user_tournaments = await user_service.get_user_tournament_registrations(user)

        tournaments = tournament_data['all_tournaments']
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

        # Personal-info autosave. The free-text fields debounce to coalesce
        # keystrokes; ``personal_dirty`` tracks whether that debounced write is
        # still pending so a blur flush (or the discrete DM toggle) can commit it
        # immediately — otherwise tabbing or navigating away inside the 0.8s
        # window silently drops the last edit (the beforeunload guard only warns,
        # and never fires at all for an in-app tab switch).
        personal_token = {'n': 0}
        personal_dirty = {'v': False}

        async def save_personal():
            if not personal_dirty['v']:
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
            personal_dirty['v'] = False
            show_saved()
            mark_clean()

        async def on_personal_typing():
            mark_dirty()
            personal_dirty['v'] = True
            personal_token['n'] += 1
            mine = personal_token['n']
            await asyncio.sleep(0.8)
            if mine != personal_token['n']:
                return
            await save_personal()

        async def flush_personal():
            # Bump the token so an in-flight debounce coroutine bails instead of
            # firing a duplicate save after this immediate one.
            personal_token['n'] += 1
            await save_personal()

        async def on_dm_change():
            # A checkbox toggle is a discrete commit — save at once rather than
            # leaving it in the debounce window where a quick nav could lose it.
            mark_dirty()
            personal_dirty['v'] = True
            personal_token['n'] += 1
            await save_personal()

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

        # Identity header — who you are, so the page reads as a profile rather
        # than jumping straight into an unlabeled edit form.
        with ui.row().classes('items-center gap-4 w-full no-wrap'):
            avatar_url = app.storage.user.get('avatar')
            if avatar_url:
                ui.image(avatar_url).props('width=64px height=64px fit=cover round') \
                    .classes('shrink-0')
            else:
                ui.icon('account_circle', size='64px').classes('text-primary shrink-0')
            with ui.column().classes('gap-0 col'):
                ui.label(user.preferred_name).classes('page-title')
                with ui.row().classes('items-center gap-2'):
                    ui.label(f'@{user.username}').classes('text-muted text-caption')
                    if user.pronouns:
                        ui.badge(user.pronouns).props('outline color=grey')

        # Auto-save status indicator (updated by the on_change handlers above).
        with ui.row().classes('items-center gap-1'):
            status_icon = ui.icon('check_circle', size='xs').classes('text-muted')
            status_label = ui.label('Changes save automatically').classes('text-muted text-caption')

        # Personal Information Section
        with ui.card().classes('card-full-width'):
            ui.label('Personal information').classes('section-title')

            # Two-up on desktop; the .form-grid media query collapses it to a
            # single column below 600px so neither field is squeezed on a phone.
            with ui.grid(columns=2).classes('form-grid'):
                display_name_hint = f"Default: {user.username}" if not user.display_name else ""
                with ui.column().classes('gap-1'):
                    ui.label('Display Name').classes('input-label')
                    display_name_input = ui.input(
                        '',
                        value=user.display_name or '',
                        placeholder=display_name_hint,
                        on_change=on_personal_typing,
                    ).classes('input-full-width').props('outlined dense')
                    display_name_input.on('blur', flush_personal)

                with ui.column().classes('gap-1'):
                    ui.label('Pronouns').classes('input-label')
                    pronouns_input = ui.input(
                        '',
                        value=user.pronouns or '',
                        placeholder='e.g. they/them',
                        on_change=on_personal_typing,
                    ).classes('input-full-width').props('outlined dense')
                    pronouns_input.on('blur', flush_personal)

        # Notifications — all channels together (Discord DM, this device) plus
        # per-tournament granularity, so "how do I get notified" lives in one place.
        with ui.card().classes('card-full-width'):
            ui.label('Notifications').classes('section-title')
            ui.label('Choose how Wizzrobe reaches you about matches, crew, and shifts.') \
                .classes('text-muted text-caption')

            ui.label('Discord').classes('subsection-title q-mt-sm')
            dm_checkbox = ui.checkbox(
                'Receive Discord DM notifications for match updates',
                value=user.dm_notifications,
                on_change=on_dm_change,
            )

            # Device notifications (web push) render inline here as a second
            # channel; the section self-hides when VAPID keys aren't configured.
            await render_web_push_section(user)

            # Per-tournament match alerts can be a long list, so tuck them behind
            # an expansion; the Discord toggle above is the master switch.
            with ui.expansion('Per-tournament match alerts', icon='tune').classes('w-full q-mt-sm') \
                    .props('header-class=text-weight-bold'):
                ui.label(
                    'Fine-tune which matches trigger a DM, per tournament. '
                    '"Streamed & Candidates" also alerts you when a match may be streamed.'
                ).classes('text-caption text-grey-7')
                if not active_tournaments:
                    ui.label('No active tournaments.').classes('text-muted')
                else:
                    for tournament in active_tournaments:
                        existing = prefs_by_tournament.get(tournament.id)
                        current_level = existing.match_notifications if existing else 'none'
                        with ui.row().classes('items-center justify-between w-full q-my-xs gap-2'):
                            ui.label(tournament.name).classes('col')
                            pref_widgets[tournament.id] = ui.select(
                                options=level_options,
                                value=current_level,
                                on_change=lambda _, tid=tournament.id: on_notification_pref_change(tid),
                            ).props('outlined dense').style('min-width: 170px')

        # Tournament enrollment — manual opt-in lists, one checkbox per row so it
        # stays tappable on mobile.
        tournament_checkboxes = {}
        staff_tournaments = [t for t in tournaments if t.staff_administered]
        player_tournaments = [t for t in tournaments if not t.staff_administered]

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

        def render_tournament_group(tournament_list, label, icon):
            if not tournament_list:
                return
            with ui.row().classes('items-center gap-2 q-mt-sm'):
                ui.icon(icon, size='sm').classes('icon-primary')
                ui.label(label).classes('subsection-title')
            for t in tournament_list:
                if t.challonge_tournament_id:
                    render_challonge_tournament(t)
                else:
                    tournament_checkboxes[t.id] = ui.checkbox(
                        t.name,
                        value=t.id in selected_tournament_ids,
                        on_change=on_tournament_change,
                    ).classes('input-full-width')

        with ui.card().classes('card-full-width'):
            ui.label('Tournament enrollment').classes('section-title')
            ui.label(
                'Join a tournament to appear in its player pool and get scheduled. '
                'Challonge-linked tournaments enroll you automatically from the bracket.'
            ).classes('text-muted text-caption')
            if not staff_tournaments and not player_tournaments:
                ui.label('No tournaments are open for enrollment right now.').classes('text-muted')
            render_tournament_group(staff_tournaments, 'Staff-administered', 'emoji_events')
            render_tournament_group(player_tournaments, 'Community', 'groups')

        # Connected accounts (Challonge / Twitch / racetime) — one compact card
        # of rows instead of three near-identical cards.
        await render_connected_accounts_section(
            user, [CHALLONGE_CONFIG, TWITCH_CONFIG, RACETIME_CONFIG]
        )

        # API token management (self-contained; collapsed developer surface).
        await render_api_tokens_section(user)
