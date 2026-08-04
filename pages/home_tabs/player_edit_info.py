"""Profile tab - a player's personal info, notifications, enrollment, and links."""

import asyncio

from nicegui import app, background_tasks, context, ui

from application.services import (
    AuthService,
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
from theme.help import help_icon


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

        # Signing up happens on the Tournaments tab now; what is still needed
        # here is which tournaments the player is in, so the match-alert rows
        # below can mark them.
        user_tournaments = await user_service.get_user_tournament_registrations(user)
        selected_tournament_ids = [tp.tournament_id for tp in user_tournaments]

        # This tab is not itself flag-gated, so the Challonge row in Connected
        # accounts has to be skipped when the community lacks the feature.
        live_flags = await FeatureFlagService().enabled_flags()
        challonge_live = FeatureFlag.CHALLONGE in live_flags
        # The Matcherino handle only means anything where prize money is paid,
        # so a community without payouts is not asked for one.
        payouts_live = FeatureFlag.PAYOUTS in live_flags

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
                    matcherino_username=(
                        matcherino_input.value if payouts_live else None
                    ),
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
            with ui.row().classes('items-center gap-1 no-wrap'):
                ui.label('Notifications').classes('section-title')
                await help_icon('notification-settings')
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
                    'match may be streamed. To play in one, sign up on the Tournaments tab.'
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

        # Connected accounts (Challonge / Twitch / racetime) — one compact card
        # of rows instead of three near-identical cards.
        link_configs = [TWITCH_CONFIG, RACETIME_CONFIG]
        if challonge_live:
            link_configs.insert(0, CHALLONGE_CONFIG)
        await render_connected_accounts_section(user, link_configs)

        # Deliberately its own card rather than a row among the linked accounts:
        # those three are verified by the provider, this one is typed in, and
        # sitting it beside them would let it read as verified too.
        if payouts_live:
            with ui.card().classes('card-full-width'):
                ui.label('Matcherino handle').classes('section-title')
                ui.label(
                    'Where prize money is sent. Copy it from your Matcherino '
                    'profile, including the number after the hash. Nobody checks '
                    'it for you, so a typo is a payout that goes nowhere.'
                ).classes('text-muted text-caption')
                matcherino_input = ui.input(
                    'Matcherino handle',
                    value=user.matcherino_username or '',
                    placeholder='e.g. yourname#123456',
                    on_change=on_personal_typing,
                ).props('outlined dense stack-label').classes('input-full-width')
                matcherino_input.on('blur', flush_personal)

        # What you sent through the feedback form and whether it was read.
        # Draws nothing when you have sent none, or when the community has the
        # feature off.
        await render_my_feedback_section(user)

        # API token management (self-contained; collapsed developer surface).
        await render_api_tokens_section(user)
