"""My Schedule — everything the viewer personally committed to, on one scroll.

Your matches, the crew slots you signed up for, when you said you can play, and
any equipment you are still holding. These were four separate tabs, which meant
the answer to "what am I doing at this event?" was spread across four taps and,
on a phone, three of them lived behind **More**.

Sections render in commitment order: what you are scheduled to play, then what
you volunteered for, then what you told staff about your time, then what you are
carrying. Every section stays open. A section whose feature the community has
turned off is not built at all.
"""

from typing import Optional

from nicegui import ui

from application.services import FeatureFlagService
from models import FeatureFlag
from pages.home_tabs.availability import availability_tab
from pages.home_tabs.equipment import equipment_checkouts_section
from pages.home_tabs.my_crew import my_crew_tab
from pages.home_tabs.player import render_player_dashboard


async def my_schedule_tab(
    schedule: Optional[int] = None,
    reschedule: Optional[int] = None,
    match: Optional[int] = None,
) -> None:
    """The three deep-link params belong to the matches section and pass straight
    through to it; see :func:`pages.home_tabs.player.render_player_dashboard` for
    what each one opens. They arrive here because the DMs that carry them predate
    this tab and address ``/home/player``, which resolves onto My Schedule via
    the alias declared in :mod:`pages.home`.
    """
    live = await FeatureFlagService().enabled_flags()

    with ui.column().classes('w-full'):
        await render_player_dashboard(
            schedule=schedule, reschedule=reschedule, match=match,
        )
        ui.separator().classes('separator-spacing')
        await my_crew_tab()
        ui.separator().classes('separator-spacing')
        await availability_tab()
        if FeatureFlag.EQUIPMENT in live:
            ui.separator().classes('separator-spacing')
            await equipment_checkouts_section()
