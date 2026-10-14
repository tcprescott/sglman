"""Home's four-tab nav, and the retired slugs that must still resolve.

Home came down from ten tabs to four. Four of the six link targets documented in
``docs/features/discord.md`` address ``/home/player``, a slug that no longer
names a tab, and a DM outlives the app version that sent it: a button that lands
on the wrong tab reads as a broken app to the person holding the phone.
"""

import pytest

from models import FeatureFlag
from pages.home_tabs.event import VIEWS, available_views, resolve_view
from application.services.nav_preference_service import DEFAULT_PINS
from theme.base import BaseLayout, tab_slug

# Every home path a Discord DM, an OAuth return, or a seeded feedback row can
# carry, mapped to the tab it must open. Sourced from docs/features/discord.md,
# application/utils/app_links.py, and pages/_oauth_link.py.
LEGACY_PATHS = {
    'player': 'My Schedule',
    'my-crew': 'My Schedule',
    'availability': 'My Schedule',
    'equipment': 'My Schedule',
    'schedule': 'Event',
    'brackets': 'Event',
    'triforce-texts': 'Tournaments',
    'profile': 'Profile',
}

# The shape pages/home.py builds. Kept here rather than imported because the
# page function needs a request, a tenant and a signed-in user to assemble it,
# none of which this test has or needs.
HOME_TABS = [
    {'label': 'Event', 'aliases': ('schedule', 'brackets', 'community')},
    {'label': 'My Schedule', 'aliases': ('player', 'my-crew', 'availability', 'equipment')},
    {'label': 'Tournaments', 'aliases': ('triforce-texts',)},
    {'label': 'Profile'},
]


def _layout(section):
    return BaseLayout(tabs=HOME_TABS, section=section)


class TestTheHomeTabsMatchThePage:
    def test_home_declares_exactly_the_four_tabs_this_test_pins(self):
        import inspect

        import pages.home as home

        src = inspect.getsource(home.create)
        for tab in HOME_TABS:
            assert f"'label': '{tab['label']}'" in src
        for tab in HOME_TABS:
            for alias in tab.get('aliases', ()):
                assert alias in src, f'{alias} is pinned here but absent from home.py'

    def test_the_default_pins_point_at_home_tabs(self):
        # Everyone starts with these pinned, which is what puts them in the phone
        # bottom bar. Rename a slug without updating the pin and it silently
        # disappears from every player's bar.
        slugs = {tab.get('slug') or tab_slug(tab['label']) for tab in HOME_TABS}
        for pin in DEFAULT_PINS:
            hub, slug = pin.strip('/').split('/')
            assert hub == 'home' and slug in slugs, pin


class TestRetiredSlugsStillResolve:
    @pytest.mark.parametrize('slug,expected', sorted(LEGACY_PATHS.items()))
    def test_a_legacy_path_opens_its_tab(self, slug, expected):
        assert _layout(slug)._default_tab == expected

    def test_a_canonical_slug_always_wins_over_an_alias(self):
        # 'schedule' is an Event alias and also the start of 'My Schedule'.
        # Whatever else happens, a live tab's own slug must reach that tab.
        for tab in HOME_TABS:
            slug = tab_slug(tab['label'])
            assert _layout(slug)._default_tab == tab['label']

    def test_an_unknown_slug_falls_back_to_the_first_tab(self):
        assert _layout('does-not-exist')._default_tab == 'Event'
        assert _layout(None)._default_tab == 'Event'

    def test_the_url_writes_back_the_canonical_slug_not_the_alias(self):
        # Aliases answer on read-in only, so arriving on /home/player and then
        # switching tabs leaves a URL naming a slug we still publish.
        layout = _layout('player')
        assert layout._slug_by_label['My Schedule'] == 'my-schedule'
        assert 'player' not in layout._slug_by_label.values()


class TestTheEventViewSwitcher:
    def test_every_view_slug_is_an_alias_on_the_event_tab(self):
        # The switcher opens on the view the URL names, so each view's slug has
        # to survive as a path. Miss one and /home/brackets opens the board.
        event = next(t for t in HOME_TABS if t['label'] == 'Event')
        assert {v.slug for v in VIEWS} == set(event['aliases'])

    def test_brackets_drops_out_when_the_community_has_it_off(self):
        assert [v.slug for v in available_views(set())] == ['schedule']
        assert 'brackets' in [v.slug for v in available_views({FeatureFlag.BRACKETS})]

    def test_a_view_the_community_turned_off_opens_the_first_one(self):
        views = available_views(set())
        assert resolve_view(views, 'brackets').slug == 'schedule'
        assert resolve_view(views, None).slug == 'schedule'

    def test_a_named_view_wins(self):
        views = available_views({FeatureFlag.BRACKETS})
        assert resolve_view(views, 'schedule').slug == 'schedule'
        assert resolve_view(views, 'brackets').slug == 'brackets'


class TestTheCommunityView:
    def test_community_drops_out_when_the_community_has_it_off(self):
        assert 'community' not in [v.slug for v in available_views({FeatureFlag.BRACKETS})]
        assert [v.slug for v in available_views({FeatureFlag.COMMUNITY_EVENTS})] == ['schedule', 'community']

    def test_the_old_listing_url_lands_on_the_view(self):
        layout = _layout('community')
        assert layout._default_tab == 'Event'
