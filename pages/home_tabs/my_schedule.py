"""My Schedule — everything the viewer personally committed to, on one scroll.

Your matches, the crew slots you signed up for, your volunteer shifts, when you
said you can play, and any equipment you are still holding. Most of these were
separate tabs, which meant the answer to "what am I doing at this event?" was spread across four taps and,
on a phone, three of them lived behind **More**.

Sections render in commitment order: what you are scheduled to play, then what
you volunteered for, then what you told staff about your time, then what you are
carrying. Every section stays open. A section whose feature the community has
turned off is not built at all.

Each is a panel (``theme/section.py``) rather than a heading over a hairline
separator. Stacked flat, the four ran together into one document while each
section's own header/separator margin left its title floating four ems above its
content — the tab was long *and* looked empty. The panel puts an edge round each
block and its controls in its own header.
"""

from typing import Optional

from nicegui import app, ui

from application.services import FeatureFlagService, TournamentService, get_user_from_session
from models import FeatureFlag
from pages.home_tabs.availability import availability_tab
from pages.home_tabs.equipment import equipment_checkouts_section
from pages.home_tabs.my_crew import my_crew_tab
from pages.home_tabs.my_volunteer_shifts import my_volunteer_shifts_section
from pages.home_tabs.player import render_player_dashboard


async def my_schedule_tab(
    schedule: Optional[int] = None,
    reschedule: Optional[int] = None,
    match: Optional[int] = None,
    hard: Optional[int] = None,
    agree: Optional[int] = None,
    book: Optional[int] = None,
    startgg: Optional[int] = None,
    comments: Optional[int] = None,
) -> None:
    """The deep-link params belong to the matches section and pass straight
    through to it; see :func:`pages.home_tabs.player.render_player_dashboard` for
    what each one opens. ``match`` also reaches the crew section, which scrolls
    to the viewer's slot on that match when they crew it rather than play it. They arrive here because the DMs that carry them predate
    this tab and address ``/home/player``, which resolves onto My Schedule via
    the alias declared in :mod:`pages.home`.
    """
    live = await FeatureFlagService().enabled_flags()
    # Someone entered in no tournament is here for their crew slots, and the
    # matches panel above them was an empty board with six help chips: on a
    # phone it pushed the crew list, and its Confirm button, below the fold.
    # Their crew comes first; the empty panel still renders after it, because
    # it is where a forwarded player link explains itself.
    user = await get_user_from_session(app.storage.user)
    plays = bool(user and await TournamentService().get_enrolled_players_by_user(user))
    volunteers = user is not None and FeatureFlag.VOLUNTEERS in live

    with ui.column().classes('page-container wiz-section-stack'):
        if not plays:
            if volunteers:
                await my_volunteer_shifts_section(user)
            await my_crew_tab(focus_match=match)
        await render_player_dashboard(
            schedule=schedule, reschedule=reschedule, match=match, hard=hard,
            agree=agree, book=book, startgg=startgg, comments=comments,
        )
        if plays:
            await my_crew_tab(focus_match=match)
            if volunteers:
                await my_volunteer_shifts_section(user)
        await availability_tab()
        if FeatureFlag.EQUIPMENT in live:
            await equipment_checkouts_section()
