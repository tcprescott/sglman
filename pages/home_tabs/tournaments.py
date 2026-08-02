"""Tournaments — where a player signs up to compete.

Signing up used to be a checkbox in a card near the bottom of the Profile tab, a
page nobody has to visit to use the app. Players who never opened it never
entered the player pool, and the only sign anything was wrong came later, when
staff went to schedule a match and found the tournament empty.

So the opt-in gets its own tab and its own card per tournament: what the
tournament is, when it runs, who else is in, and one button. Sections are
ordered by what the reader can act on — signups that are open, then what they
are already in, then the ones that have not opened or have shut.

Everything the card claims comes from ``TournamentService.list_signup_cards``,
including whether the button should be there at all, so this page and the REST
route cannot disagree about who may sign up.
"""

from typing import Optional

from nicegui import app, background_tasks, context, ui

from application.content import parse_blocks
from application.services import TournamentService, get_user_from_discord_id
from application.services.tournament_service import TournamentSignupCard
from application.utils.timezone import format_local_date, format_local_display
from application.utils.tournament_signup import SignupWindow
from theme.help import help_icon
from theme.help.render import render_blocks
from theme.notify import notify_error

# Section title, and the predicate that puts a card in it. Order is the reading
# order: what you can do something about, then what you are already in, then the
# rest. A section with no cards is not drawn.
_SECTIONS = (
    (
        'Open for signup',
        'how_to_reg',
        lambda c: not c.enrolled and c.window is SignupWindow.OPEN,
    ),
    ('My tournaments', 'emoji_events', lambda c: c.enrolled),
    (
        'Opening soon',
        'schedule',
        lambda c: not c.enrolled and c.window is SignupWindow.UPCOMING,
    ),
    (
        'Signups closed',
        'lock',
        lambda c: not c.enrolled and c.window is SignupWindow.CLOSED,
    ),
)


def signup_status(card: TournamentSignupCard) -> tuple[str, str]:
    """``(chip class, label)`` for one tournament, from the reader's side of it.

    Enrolment wins over the window: "Signed up" is the fact that matters to
    someone already in, and telling them signups closed would read as though
    they had missed it.
    """
    if card.enrolled:
        return 'wiz-chip--ok', 'Signed up'
    if card.challonge_managed:
        return 'wiz-chip--neutral', 'Roster from Challonge'
    if card.window is SignupWindow.UPCOMING:
        return 'wiz-chip--candidate', 'Not open yet'
    if card.window is SignupWindow.CLOSED:
        return 'wiz-chip--cancelled', 'Signups closed'
    return 'wiz-chip--pending', 'Signups open'


def window_note(card: TournamentSignupCard) -> Optional[str]:
    """The one line under the title that says when the window moves next."""
    t = card.tournament
    if card.window is SignupWindow.UPCOMING and t.signups_open_at:
        return f'Signups open {format_local_display(t.signups_open_at)}'
    if card.window is SignupWindow.OPEN and t.signups_close_at:
        return f'Signups close {format_local_display(t.signups_close_at)}'
    if card.window is SignupWindow.CLOSED and t.signups_close_at:
        return f'Signups closed {format_local_display(t.signups_close_at)}'
    return None


def event_dates(card: TournamentSignupCard) -> Optional[str]:
    """When the tournament itself runs, when staff have said."""
    t = card.tournament
    if t.event_start_date and t.event_end_date:
        if t.event_start_date == t.event_end_date:
            return format_local_date(t.event_start_date)
        return f'{format_local_date(t.event_start_date)} – {format_local_date(t.event_end_date)}'
    if t.event_start_date:
        return f'From {format_local_date(t.event_start_date)}'
    return None


async def tournaments_tab() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if user is None:
        ui.label('You must be logged in to sign up for tournaments.').classes('text-error')
        return

    service = TournamentService()

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row items-center full-width'):
            ui.label('Tournaments').classes('page-title')
            await help_icon('tournament-signup')
            ui.space()
        ui.label(
            'Sign up to enter a tournament\'s player pool so staff can schedule you '
            'into its matches. Following a tournament for match alerts is separate — '
            'that lives on your Profile.'
        ).classes('text-muted')
        ui.separator().classes('separator-spacing')

        # Both handlers run as detached background tasks, where the slot stack is
        # empty, so the client comes from the call site rather than being read in
        # here — ``context.client`` raises inside the task.
        async def sign_up(tournament_id: int, client) -> None:
            with client:
                try:
                    tournament = await service.self_enroll(tournament_id, user)
                    ui.notify(f"You're signed up for {tournament.name}.", color='positive')
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                await cards.refresh()

        async def withdraw(tournament_id: int, client) -> None:
            with client:
                try:
                    tournament = await service.self_withdraw(tournament_id, user)
                    ui.notify(f'You have withdrawn from {tournament.name}.', color='positive')
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                await cards.refresh()

        def render_card(card: TournamentSignupCard) -> None:
            t = card.tournament
            chip_class, status = signup_status(card)
            with ui.card().classes('full-width q-mb-sm'):
                with ui.row().classes('items-center gap-2 flex-wrap full-width'):
                    ui.label(t.name).classes('text-subtitle1 text-weight-medium')
                    with ui.element('span').classes(f'wiz-chip {chip_class}'):
                        ui.label(status)
                    ui.space()
                    dates = event_dates(card)
                    if dates:
                        with ui.element('span').classes('wiz-chip wiz-chip--neutral'):
                            ui.icon('event', size='14px')
                            ui.label(dates)

                note = window_note(card)
                if note:
                    ui.label(note).classes('text-caption text-grey-7')

                if t.description:
                    # Parsed to blocks and drawn element by element rather than
                    # through ui.markdown: this is staff-authored prose reaching a
                    # player's browser, so it renders as element content, never as
                    # markup. Same renderer the help and event-info pages use.
                    with ui.element('div').classes('wiz-help-prose'):
                        render_blocks(parse_blocks(t.description))

                if t.rules_url:
                    ui.link('Rules', t.rules_url, new_tab=True).classes('text-caption')

                with ui.expansion(
                    f'{card.entrant_count} signed up', icon='group',
                ).classes('w-full').props('dense'):
                    if not card.entrants:
                        ui.label('Nobody yet — be first.').classes('text-muted text-caption')
                    for entrant in card.entrants:
                        ui.label(entrant.display_name or entrant.username) \
                            .classes('text-caption')

                with ui.row().classes('items-center gap-2'):
                    if card.can_sign_up:
                        ui.button(
                            'Sign up', icon='how_to_reg',
                            on_click=lambda _e, tid=t.id: background_tasks.create(
                                sign_up(tid, context.client)),
                        ).props('color=primary no-caps')
                    elif card.can_withdraw:
                        ui.button(
                            'Withdraw', icon='undo',
                            on_click=lambda _e, tid=t.id: background_tasks.create(
                                withdraw(tid, context.client)),
                        ).props('flat color=negative dense no-caps')
                    elif card.challonge_managed:
                        ui.label(
                            'Enrolment follows the Challonge bracket — link your '
                            'Challonge account on your Profile.'
                        ).classes('text-caption text-grey-7')
                    elif card.enrolled:
                        # Enrolled with the window shut. Saying nothing here reads
                        # as a missing button, so the card says whose call it is.
                        ui.label(
                            'Signups have closed — ask staff if you need to drop out.'
                        ).classes('text-caption text-grey-7')

        @ui.refreshable
        async def cards() -> None:
            all_cards = await service.list_signup_cards(user)
            if not all_cards:
                ui.label(
                    'No tournaments are running right now. Check back when staff '
                    'have set one up.'
                ).classes('text-muted')
                return
            for title, icon, predicate in _SECTIONS:
                section = [c for c in all_cards if predicate(c)]
                if not section:
                    continue
                with ui.row().classes('items-center gap-2 q-mt-md'):
                    ui.icon(icon, size='sm').classes('icon-primary')
                    ui.label(title).classes('subsection-title')
                for card in section:
                    render_card(card)

        await cards()
