"""Wiring tests for the cat-fact surfaces.

The facts themselves are covered in ``test_utils_coverage.py``. What is asserted
here is where they *appear*, because every one of these is a silent failure: a
``/cat-facts`` page that joins ``protected_routes`` bounces anonymous visitors to
Discord OAuth, and a waiting spinner that loses its fact just goes back to being
a blank screen without anything failing.
"""

import inspect
import re

import pages.cat_facts as cat_facts_page
import theme.base as base
import theme.waiting as waiting
from middleware.auth import protected_routes
from pages.admin_tabs.reports import shared as report_shared
from theme.dialog.cat_fact_dialog import CatFactDialog


class TestCatFactsPage:
    def test_registers_the_route_as_public(self):
        source = inspect.getsource(cat_facts_page.create)
        assert "@public_page('/cat-facts')" in source

    def test_route_never_joins_protected_routes(self):
        """A signed-out visitor following a shared link must reach the page."""
        cat_facts_page.create()
        assert '/cat-facts' not in protected_routes

    def test_page_tolerates_an_anonymous_visitor(self):
        """``public_page`` contract: nothing here may dereference ``user``, which
        is ``None`` for the signed-out visitor the page exists to serve."""
        source = inspect.getsource(cat_facts_page.create)
        # Excludes app.storage.user, which is a dict and always present.
        assert not re.search(r'(?<!storage\.)\buser\.\w', source)

    def test_frontend_registers_the_page(self):
        with open('frontend.py', encoding='utf-8') as fh:
            frontend_source = fh.read()
        assert 'cat_facts.create()' in frontend_source

    def test_stays_out_of_the_drawer_nav(self):
        """Deliberately undiscoverable: the page is found, not advertised."""
        assert '/cat-facts' not in inspect.getsource(base)


class TestCatFactDialog:
    def test_offers_a_route_to_the_full_list(self):
        source = inspect.getsource(CatFactDialog)
        assert "ui.navigate.to('/cat-facts')" in source

    def test_reroll_excludes_the_fact_on_screen(self):
        assert 'exclude=' in inspect.getsource(CatFactDialog._reroll)


class TestWaitingPanel:
    def test_panel_carries_a_cat_fact(self):
        assert 'random_cat_fact' in inspect.getsource(waiting.waiting_panel)

    def test_deferred_tab_build_uses_the_panel(self):
        """The bare ui.spinner it replaced showed nothing to read."""
        assert 'waiting_panel' in inspect.getsource(base.BaseLayout._build_tab)

    def test_report_busy_overlay_carries_a_fact(self):
        assert 'random_cat_fact' in inspect.getsource(report_shared.show_navigating)


class TestAuthWaitScreens:
    def test_oauth_callback_and_claim_both_show_a_panel(self):
        with open('pages/auth.py', encoding='utf-8') as fh:
            source = fh.read()
        assert "waiting_panel('Signing you in…')" in source
        assert "waiting_panel('Finishing your login…')" in source
