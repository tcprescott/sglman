"""``EventInfoService`` — the three rules the event handbook needs a service for.

The handbook is one community's own event documentation, so unlike help it is
gated three ways: the whole section behind ``EVENT_INFO``, an article behind its
own optional ``feature:``, and an article behind ``roles:``. The last one is what
lets the page stay public while the floor procedure the room staff work from is
not: the filter subtracts from what a reader sees, it never redirects them.

The ``db`` fixture provisions the default tenant (id 1, slug ``default``) with
every flag on, and that slug is the one the dev fixture handbook ships under — so
these run against real shipped content rather than a synthetic directory.
"""

import pytest

from application.errors import FeatureDisabledError
from application.services import EventInfoService
from application.tenant_context import tenant_scope
from models import Role, Tenant, UserRole
from tests.conftest import enable_all_flags
from tests.factories import make_user


@pytest.fixture
async def bare_tenant(db) -> Tenant:
    """A community with no feature-flag rows: everything optional is off."""
    return await Tenant.create(name='Bare', slug='bare')


@pytest.fixture
async def handbookless_tenant(db) -> Tenant:
    """A community granted the feature that ships no handbook directory."""
    tenant = await Tenant.create(name='Nothing Here', slug='nothing-here')
    await enable_all_flags(tenant.id)
    return tenant


async def _user_with(*roles: Role, discord_id: int = 5150):
    user = await make_user(discord_id=discord_id)
    for role in roles:
        await UserRole.create(user=user, role=role)
    return user


class TestTheSectionGate:
    async def test_listing_is_refused_where_the_feature_is_off(self, bare_tenant):
        """Not an empty list — a refusal. The service half of the gate is what
        stops a caller with no gate of its own reaching the section at all."""
        with tenant_scope(bare_tenant.id):
            with pytest.raises(FeatureDisabledError):
                await EventInfoService.list_articles()

    async def test_fetching_an_article_is_refused_where_the_feature_is_off(self, bare_tenant):
        with tenant_scope(bare_tenant.id):
            with pytest.raises(FeatureDisabledError):
                await EventInfoService.get_article('attending')

    async def test_fetching_a_snippet_is_refused_where_the_feature_is_off(self, bare_tenant):
        with tenant_scope(bare_tenant.id):
            with pytest.raises(FeatureDisabledError):
                await EventInfoService.get_snippet('check-in')


class TestTenantScoping:
    async def test_a_community_sees_its_own_handbook(self, db):
        slugs = {a.slug for a in await EventInfoService.list_articles()}
        assert 'attending' in slugs

    async def test_a_community_with_no_handbook_sees_nothing(self, handbookless_tenant):
        """An empty section, not an error. A community that has just been granted
        the feature and written nothing is exactly this state."""
        with tenant_scope(handbookless_tenant.id):
            assert await EventInfoService.list_articles() == []
            assert await EventInfoService.get_article('attending') is None

    async def test_one_communitys_article_is_not_readable_from_another(self, handbookless_tenant):
        """The isolation that matters here: content is filed under the tenant's
        slug, so a granted community must not read a neighbour's handbook."""
        with tenant_scope(handbookless_tenant.id):
            assert await EventInfoService.get_article('proctoring') is None
            assert await EventInfoService.get_snippet('check-in') is None

    async def test_an_unknown_slug_is_none(self, db):
        assert await EventInfoService.get_article('no-such-article') is None


class TestRoleGating:
    async def test_a_role_gated_article_is_hidden_from_a_signed_out_reader(self, db):
        slugs = {a.slug for a in await EventInfoService.list_articles()}
        assert 'proctoring' not in slugs

    async def test_a_role_gated_article_is_hidden_from_a_reader_without_the_role(self, db):
        user = await _user_with(Role.TRIFORCE_SUBMITTER)
        slugs = {a.slug for a in await EventInfoService.list_articles(user)}
        assert 'proctoring' not in slugs

    @pytest.mark.parametrize('role', [Role.VOLUNTEER, Role.PROCTOR, Role.STAFF])
    async def test_any_one_of_the_named_roles_is_enough(self, db, role):
        """Roles are an OR, matching the Volunteer hub's own gate — a proctor who
        was never given the Volunteer role still needs the room procedure."""
        user = await _user_with(role)
        slugs = {a.slug for a in await EventInfoService.list_articles(user)}
        assert 'proctoring' in slugs

    async def test_fetching_a_role_gated_article_directly_is_refused(self, db):
        """Same answer as a missing article: a reader should not learn that a
        page exists for people with more access than them."""
        assert await EventInfoService.get_article('proctoring') is None
        user = await _user_with(Role.PROCTOR)
        assert await EventInfoService.get_article('proctoring', user) is not None

    async def test_a_public_article_stays_readable_signed_out(self, db):
        assert await EventInfoService.get_article('attending') is not None


class TestSnippets:
    async def test_a_public_snippet_resolves_signed_out(self, db):
        snippet = await EventInfoService.get_snippet('check-in')
        assert snippet is not None
        assert snippet.article_slug == 'attending'

    async def test_a_snippet_links_back_into_its_own_section(self, db):
        """A popup opened from a handbook snippet must not send the reader to
        ``/help`` — the article it is quoting does not live there."""
        snippet = await EventInfoService.get_snippet('check-in')
        assert snippet.href.startswith('/event-info/attending')

    async def test_a_snippet_inherits_its_articles_role_gate(self, db):
        """A snippet is a region of an article, so it can never be more readable
        than the article it was cut from."""
        assert await EventInfoService.get_snippet('proctor-handover') is None
        user = await _user_with(Role.PROCTOR)
        assert await EventInfoService.get_snippet('proctor-handover', user) is not None

    async def test_an_unknown_snippet_is_none(self, db):
        assert await EventInfoService.get_snippet('no-such-snippet') is None
