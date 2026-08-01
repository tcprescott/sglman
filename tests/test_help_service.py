"""``HelpService`` — the one rule the static help catalogue needs a service for.

An article that documents an optional subsystem must not reach a community that
has the subsystem switched off. Someone reading "open the Volunteer tab" and
finding no Volunteer tab is worse served than someone who never saw the article,
and the same goes for a help icon that would open a popup describing a control
they cannot reach.

The ``db`` fixture pre-seeds the default tenant (id 1) with every flag on, so the
off-state is exercised under a freshly created tenant, which starts with no flag
rows — a missing row is the disabled-by-default posture.
"""

import pytest

from application.services import HelpService
from application.tenant_context import tenant_scope
from models import Tenant


@pytest.fixture
async def bare_tenant(db) -> Tenant:
    """A community with no feature-flag rows: everything optional is off."""
    return await Tenant.create(name='Bare', slug='bare')


class TestArticleGating:
    async def test_a_flagged_article_is_offered_where_the_feature_is_live(self, db):
        slugs = {a.slug for a in await HelpService.list_articles()}
        assert 'volunteering' in slugs
        assert 'crew' in slugs

    async def test_a_flagged_article_is_withheld_where_the_feature_is_off(self, bare_tenant):
        with tenant_scope(bare_tenant.id):
            slugs = {a.slug for a in await HelpService.list_articles()}
        assert 'volunteering' not in slugs

    async def test_ungated_articles_survive_a_community_with_nothing_enabled(self, bare_tenant):
        """Help for the core surfaces is never optional — a community with every
        flag off still has players, crew and a schedule board."""
        with tenant_scope(bare_tenant.id):
            slugs = {a.slug for a in await HelpService.list_articles()}
        assert {'getting-started', 'schedule-board', 'crew', 'player', 'glossary'} <= slugs

    async def test_fetching_a_gated_article_directly_is_refused(self, bare_tenant):
        """Same answer as a missing article, deliberately: a reader following a
        stale link should not learn which features this community has off."""
        with tenant_scope(bare_tenant.id):
            assert await HelpService.get_article('volunteering') is None

    async def test_an_unknown_slug_is_none(self, db):
        assert await HelpService.get_article('no-such-article') is None


class TestSnippetGating:
    async def test_a_snippet_from_a_live_article_resolves(self, db):
        snippet = await HelpService.get_snippet('crew-status')
        assert snippet is not None
        assert snippet.article_slug == 'crew'

    async def test_a_snippet_from_a_gated_article_is_withheld(self, bare_tenant):
        """This is what makes ``help_icon`` render nothing rather than a popup
        explaining a tab the reader has no access to."""
        with tenant_scope(bare_tenant.id):
            assert await HelpService.get_snippet('shift-release') is None

    async def test_an_unknown_snippet_is_none_rather_than_raising(self, db):
        assert await HelpService.get_snippet('no-such-snippet') is None


class TestSearch:
    async def test_an_empty_query_returns_everything_available(self, db):
        assert await HelpService.search('   ') == await HelpService.list_articles()

    async def test_search_respects_the_feature_gate(self, bare_tenant):
        """Otherwise search is a way around the gate the listing applies."""
        with tenant_scope(bare_tenant.id):
            hits = await HelpService.search('shift')
        assert 'volunteering' not in {a.slug for a in hits}

    async def test_search_is_case_insensitive(self, db):
        lower = {a.slug for a in await HelpService.search('commentator')}
        upper = {a.slug for a in await HelpService.search('COMMENTATOR')}
        assert lower == upper and lower

    async def test_every_term_must_match(self, db):
        both = {a.slug for a in await HelpService.search('crew zzzznotaword')}
        assert both == set()
