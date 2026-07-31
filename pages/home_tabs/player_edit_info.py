"""Profile tab - a player's personal info, notifications, enrollment, and links."""

import asyncio

from nicegui import app, background_tasks, context, ui

from application.services import (
    AuthService,
    ChallongeService,
    FeatureFlagService,
    TimezoneService,
    TournamentNotificationService,
    UserService,
    get_user_from_discord_id,
)
from application.services.timezone_service import COMMON_TIMEZONES, MODE_PINNED
from models import FeatureFlag
from pages.home_tabs._link_section import render_connected_accounts_section
from pages.home_tabs.api_tokens_section import render_api_tokens_section
from pages.home_tabs.challonge_link_section import CONFIG as CHALLONGE_CONFIG
from pages.home_tabs.my_feedback_section import render_my_feedback_section
from pages.home_tabs.racetime_link_section import CONFIG as RACETIME_CONFIG
from pages.home_tabs.twitch_link_section import CONFIG as TWITCH_CONFIG
from pages.home_tabs.web_push_section import render_web_push_section


async def render_edit_info_tab():
    """Render the profile tab for players to update their information."""
    # Initialize service
    user_service = UserService()

    tz_settings = await TimezoneService.get_settings()
    tz_pinned = tz_settings['mode'] == MODE_PINNED
    # '' is "detect from my device" — the default, and what clearing returns to.
    tz_options = {'': 'Detect automatically from my device'}
    tz_options.update({name: name for name in COMMON_TIMEZONES})

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

    # gap-2, not gap-4: .card-full-width already carries margin-bottom: 1.5em, so a
    # 1rem column gap on top of it double-spaced every card down a page that is
    # already mostly whitespace. The gap still separates the header/status rows.
    with ui.column().classes('page-container-form gap-2'):
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

        # Per-tenant grants, for the identity header (excludes the global
        # SUPER_ADMIN, which isn't a community role).
        roles = await AuthService.get_roles(user)

        # Get tournaments and user registrations from service
        tournament_data = await user_service.get_active_tournaments_categorized()
        user_tournaments = await user_service.get_user_tournament_registrations(user)

        tournaments = tournament_data['all_tournaments']
        selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]

        # Challonge-linked tournaments handle participation automatically via the
        # bracket mirror, so their opt-in checkbox is read-only and reflects
        # bracket membership rather than a manual choice. This tab is not itself
        # flag-gated, so every Challonge call it makes has to be skipped when the
        # community lacks the feature — the service refuses otherwise.
        challonge_live = FeatureFlag.CHALLONGE in await FeatureFlagService().enabled_flags()
        account_linked = bool(user.challonge_user_id)
        challonge_participant_ids = (
            await ChallongeService().participant_tournament_ids(user) if challonge_live else set()
        )
        # Existing manual enrollments for linked tournaments must be preserved
        # untouched when the player edits their other (manual) selections.
        challonge_enrolled_ids = {
            t.id for t in tournaments
            if challonge_live and t.challonge_tournament_id and t.id in selected_tournament_ids
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

        async def save_timezone(client):
            # Its own save path, not part of the debounced personal-info bundle:
            # the zone changes what every timestamp on the page reads, so it takes
            # effect on a reload rather than silently mid-session.
            with client:
                chosen = tz_select.value or None
                if (chosen or None) == (user.timezone or None):
                    return
                show_saving()
                try:
                    await TimezoneService.set_user_timezone(user, chosen)
                except ValueError as e:
                    show_error(str(e))
                    ui.notify(str(e), color='warning')
                    return
                show_saved()
                ui.navigate.reload()

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
            # Defined further down (the notifications card); resolved at call time.
            delivery_off_note.refresh()

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
            with ui.column().classes('gap-0 col min-w-0'):
                ui.label(user.preferred_name).classes('page-title')
                with ui.row().classes('items-center gap-2'):
                    ui.label(f'@{user.username}').classes('text-muted text-caption')
                    if user.pronouns:
                        ui.badge(user.pronouns).props('outline color=grey')
                # Roles this community has granted, so the header carries something
                # the app bar doesn't already show. Per-tenant, so it reads as
                # "who you are *here*"; a player with no grants gets nothing.
                if roles:
                    with ui.row().classes('items-center gap-1 wrap q-mt-xs'):
                        for role in sorted(r.value for r in roles):
                            ui.badge(role.replace('_', ' ').title()).props('outline color=primary')

        # Auto-save status indicator (updated by the on_change handlers above).
        with ui.row().classes('items-center gap-1 q-mt-sm'):
            status_icon = ui.icon('check_circle', size='xs').classes('text-muted')
            status_label = ui.label('Changes save automatically').classes('text-muted text-caption')

        # Personal Information Section
        with ui.card().classes('card-full-width'):
            ui.label('Personal information').classes('section-title')

            # Two-up on desktop; the .form-grid media query collapses it to a
            # single column below 600px so neither field is squeezed on a phone.
            #
            # Each field carries its caption as its own Quasar label rather than a
            # preceding ui.label: an empty label prop still sets q-field--labeled,
            # which suppresses the placeholder entirely (so the hints below never
            # rendered) and overwrites the input's accessible name with ''.
            # ``stack-label`` keeps the caption above the box, as the old layout had it.
            with ui.grid(columns=2).classes('form-grid'):
                display_name_input = ui.input(
                    'Display name',
                    value=user.display_name or '',
                    placeholder=user.username,
                    on_change=on_personal_typing,
                ).props('outlined dense stack-label').classes('input-full-width')
                display_name_input.props(
                    f'hint="Shown on schedules, brackets, and crew lists. Defaults to {user.username}."'
                )
                display_name_input.on('blur', flush_personal)

                pronouns_input = ui.input(
                    'Pronouns',
                    value=user.pronouns or '',
                    placeholder='e.g. they/them',
                    on_change=on_personal_typing,
                ).props('outlined dense stack-label hint="Shown next to your name. Leave blank to omit."') \
                    .classes('input-full-width')
                pronouns_input.on('blur', flush_personal)

                # Only meaningful when the community follows each member's clock;
                # when it pins one, this control would promise something it cannot
                # deliver, so it is replaced by a note saying so.
                if tz_pinned:
                    ui.label(
                        f'Times are shown in {tz_settings["name"]} for everyone in '
                        'this community.'
                    ).classes('text-caption text-grey q-mt-sm')
                else:
                    # A saved zone outside the shortlist must survive a re-save.
                    if user.timezone and user.timezone not in tz_options:
                        tz_options[user.timezone] = user.timezone
                    tz_select = ui.select(
                        tz_options, value=user.timezone or '',
                        label='Timezone', with_input=True,
                        on_change=lambda _: background_tasks.create(
                            save_timezone(context.client)
                        ),
                    ).props('outlined dense stack-label').classes('input-full-width')
                    tz_select.props(
                        'hint="Times are shown in this timezone. '
                        'Leave on Detect automatically to follow your device."'
                    )

        # Notifications — the delivery master switch, the per-device channel, and
        # per-tournament granularity, so "how do I get notified" lives in one place.
        with ui.card().classes('card-full-width'):
            ui.label('Notifications').classes('section-title')
            ui.label('Choose whether and where Wizzrobe reaches you about your matches.') \
                .classes('text-muted text-caption')

            # Not labelled "Discord": device push is a *mirror* of the DM send path
            # (discord_service.send_dm), and every call site gates on
            # dm_notifications before reaching it — so this one checkbox governs
            # both channels. Presenting it as Discord-only made unchecking it look
            # like a way to move notifications onto the phone instead of silencing
            # them everywhere.
            ui.label('Delivery').classes('subsection-title q-mt-sm')
            dm_checkbox = ui.checkbox(
                'Send me notifications about match updates',
                value=user.dm_notifications,
                on_change=on_dm_change,
            )
            ui.label('Delivered as a Discord DM, and mirrored to any devices you add below.') \
                .classes('text-caption text-grey-7 q-ml-lg')

            @ui.refreshable
            def delivery_off_note() -> None:
                if dm_checkbox.value:
                    return
                with ui.row().classes('items-center gap-2 q-mt-sm no-wrap'):
                    ui.icon('notifications_off', size='sm').classes('text-warning')
                    ui.label(
                        'Notifications are off. Neither Discord DMs nor device '
                        'notifications will be sent, whatever the settings below say.'
                    ).classes('text-caption text-warning col')

            delivery_off_note()

            # Device notifications (web push) render inline here as a delivery
            # target; the section self-hides when VAPID keys aren't configured.
            await render_web_push_section(user)

            # An alert level is a *follow*, not a consequence of enrollment —
            # get_match_notification_subscribers never checks the player pool — so
            # the list deliberately spans every active tournament and marks the ones
            # the player is enrolled in rather than filtering down to them.
            with ui.expansion('Match alerts by tournament', icon='tune').classes('w-full q-mt-sm') \
                    .props('header-class=text-weight-bold'):
                ui.label(
                    'Follow a tournament to hear when its matches are scheduled — you do not '
                    'have to be playing in it. "Streamed & Candidates" also alerts you when a '
                    'match may be streamed.'
                ).classes('text-caption text-grey-7')
                if not active_tournaments:
                    ui.label('No active tournaments.').classes('text-muted')
                else:
                    for tournament in active_tournaments:
                        existing = prefs_by_tournament.get(tournament.id)
                        current_level = existing.match_notifications if existing else 'none'
                        with ui.row().classes('items-center justify-between w-full q-my-xs gap-2'):
                            with ui.row().classes('items-center gap-2 col min-w-0'):
                                ui.label(tournament.name).classes('ellipsis')
                                if tournament.id in selected_tournament_ids:
                                    ui.badge('Enrolled').props('outline color=primary')
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
            # Quasar's disabled checkbox is only a slight opacity change, so on its
            # own the row is indistinguishable from the editable ones beside it. A
            # lock glyph and an "Automatic" badge carry the read-only state, and the
            # explanatory lines are indented under the row rather than emitted as
            # card-level siblings where they read as unattached prose.
            with ui.row().classes('items-center gap-2 no-wrap w-full'):
                checkbox = ui.checkbox(t.name, value=in_bracket)
                checkbox.props('disable')
                checkbox.tooltip('Enrollment for this tournament is managed automatically through Challonge.')
                ui.icon('lock', size='xs').classes('text-grey-6')
                ui.badge('Automatic').props('outline color=grey')
            with ui.column().classes('gap-1 q-ml-lg'):
                if account_linked:
                    ui.label(
                        'Enrolled from the Challonge bracket — nothing to change here.'
                        if in_bracket else
                        'You are not in this bracket yet. Enrollment follows the bracket automatically.'
                    ).classes('text-caption text-grey-7')
                else:
                    ui.label('Link your Challonge account to be enrolled automatically.').classes(
                        'text-caption text-grey-7'
                    )
                    ui.button(
                        'Link Challonge account', icon='link',
                        on_click=lambda: ui.navigate.to('/challonge/link'),
                    ).props('flat dense color=primary size=sm')
                if t.challonge_tournament_url:
                    ui.link('View bracket', t.challonge_tournament_url, new_tab=True).classes('text-caption')

        def render_tournament_group(tournament_list, label, icon):
            if not tournament_list:
                return
            with ui.row().classes('items-center gap-2 q-mt-sm'):
                ui.icon(icon, size='sm').classes('icon-primary')
                ui.label(label).classes('subsection-title')
            for t in tournament_list:
                if challonge_live and t.challonge_tournament_id:
                    render_challonge_tournament(t)
                else:
                    tournament_checkboxes[t.id] = ui.checkbox(
                        t.name,
                        value=t.id in selected_tournament_ids,
                        on_change=on_tournament_change,
                    ).classes('input-full-width')

        with ui.card().classes('card-full-width'):
            ui.label('Tournament enrollment').classes('section-title')
            # Says what enrollment is *not*, because the same tournaments also
            # appear under Match alerts above and the two lists look like duplicates.
            blurb = (
                'Join a tournament to appear in its player pool and get scheduled. '
                'This is separate from match alerts — you can follow a tournament '
                'without playing in it.'
            )
            if challonge_live:
                blurb += ' Challonge-linked tournaments enroll you automatically from the bracket.'
            ui.label(blurb).classes('text-muted text-caption')
            if not staff_tournaments and not player_tournaments:
                ui.label('No tournaments are open for enrollment right now.').classes('text-muted')
            render_tournament_group(staff_tournaments, 'Staff-administered', 'emoji_events')
            render_tournament_group(player_tournaments, 'Community', 'groups')

        # Connected accounts (Challonge / Twitch / racetime) — one compact card
        # of rows instead of three near-identical cards.
        link_configs = [TWITCH_CONFIG, RACETIME_CONFIG]
        if challonge_live:
            link_configs.insert(0, CHALLONGE_CONFIG)
        await render_connected_accounts_section(user, link_configs)

        # What you sent through the feedback form and whether it was read.
        # Draws nothing when you have sent none, or when the community has the
        # feature off.
        await render_my_feedback_section(user)

        # API token management (self-contained; collapsed developer surface).
        await render_api_tokens_section(user)
