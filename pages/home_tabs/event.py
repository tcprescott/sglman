"""Event — the community's schedule, in whichever of three readings you want.

The match board, today's stage timeline, and the bracket browser used to be
three sibling tabs. On a phone that spent three of the four bottom-nav slots on
views of the same thing and pushed the player's own matches behind **More**, so
they are one tab now with a switcher across the top.

Which view opens is driven by the incoming section slug, so the retired
``/home/on-air`` and ``/home/brackets`` paths still land where they always did
(see the ``aliases`` on the Event tab in :mod:`pages.home`).
"""

from typing import Awaitable, Callable, NamedTuple, Optional

from nicegui import ui

from application.services import FeatureFlagService
from models import FeatureFlag
from pages.home_tabs.brackets import brackets_tab
from pages.home_tabs.schedule import schedule as schedule_view
from pages.home_tabs.stage_timeline import stage_timeline_tab


class EventView(NamedTuple):
    """One reading of the schedule, and what it takes to be offered."""

    slug: str
    label: str
    icon: str
    build: Callable[[], Awaitable[None]]
    # None = always offered. Otherwise the view is absent where the community
    # has that feature off, rather than the whole tab disappearing.
    flag: Optional[FeatureFlag] = None


# Order is the reading order: the whole schedule, then the day being run, then
# the tournament structure behind it.
VIEWS: tuple[EventView, ...] = (
    EventView('schedule', 'Schedule', 'schedule', schedule_view),
    EventView('on-air', 'On Air', 'live_tv', stage_timeline_tab),
    EventView('brackets', 'Brackets', 'account_tree', brackets_tab, FeatureFlag.BRACKETS),
)


def available_views(live: set) -> list[EventView]:
    """The views this community offers, in reading order.

    Pure, so the flag-gating is testable without building a page.
    """
    return [v for v in VIEWS if v.flag is None or v.flag in live]


def resolve_view(views: list[EventView], slug: Optional[str]) -> EventView:
    """The view ``slug`` names, else the first one on offer.

    Falls back rather than raising: ``slug`` arrives from the URL, and a stale
    bookmark to a view the community has since turned off should open the tab,
    not an error.
    """
    return next((v for v in views if v.slug == slug), views[0])


async def event_tab(view: Optional[str] = None) -> None:
    live = await FeatureFlagService().enabled_flags()
    views = available_views(live)
    state = {'slug': resolve_view(views, view).slug}

    @ui.refreshable
    async def body() -> None:
        await resolve_view(views, state['slug']).build()

    def switch(value: str) -> None:
        state['slug'] = value
        body.refresh()

    with ui.column().classes('w-full'):
        # A switcher over one option is just a label taking up room.
        if len(views) > 1:
            with ui.row().classes('q-px-md q-pt-md'):
                ui.toggle(
                    {v.slug: v.label for v in views},
                    value=state['slug'],
                    on_change=lambda e: switch(e.value),
                ).props('no-caps dense unelevated color=primary')
        await body()
