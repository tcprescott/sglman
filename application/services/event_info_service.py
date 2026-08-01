"""Which event-handbook articles this community's readers should see.

Three rules, which is why this is a service rather than a bare loader:

* the whole section is behind ``EVENT_INFO``, so a community that has not been
  granted it reaches nothing here — including through a caller that forgot to
  gate itself;
* an individual article may name a **feature** of its own, exactly as a help
  article can. An article that says "sign up for a shift on the Volunteer tab"
  must not be offered where there is no Volunteer tab; and
* an article may name **roles**. The floor procedure a proctor works from is not
  written for the general public — it is the standard the people running the
  room are held to, and it reads as bewildering house rules to anyone else. An
  article with roles is invisible to a reader who holds none of them, signed out
  or signed in, which is why the page can stay public.

Read-only and stateless; no repository of its own beyond the tenant lookup,
because in v1 there is no stored handbook. When the content moves into the
database this interface is the seam it lands on — the surfaces above call
``list_articles``/``get_article`` and know nothing about where the words live.
"""

from __future__ import annotations

from typing import Optional

from application.content import ContentArticle, ContentSnippet
from application.event_info import article_for_tenant, articles_for_tenant, snippet_for_tenant
from application.feature_flags import requires_feature
from application.repositories import TenantRepository
from application.services.auth_service import AuthService
from application.services.feature_flag_service import FeatureFlagService
from application.tenant_context import require_tenant_id
from models import FeatureFlag, Role, User

__all__ = ['EventInfoService']


class EventInfoService:
    """Feature- and role-aware access to the current community's event handbook."""

    @staticmethod
    async def _tenant_slug() -> str:
        tenant = await TenantRepository.get_by_id(require_tenant_id())
        return tenant.slug if tenant else ''

    @staticmethod
    async def _reader_roles(user: Optional[User]) -> set[Role]:
        """The roles to judge ``user`` by here. Signed out is simply no roles."""
        return await AuthService.get_roles(user) if user else set()

    @staticmethod
    def _readable(article: ContentArticle, live: set, roles: set[Role]) -> bool:
        if article.feature is not None and article.feature not in live:
            return False
        return not article.roles or bool(roles.intersection(article.roles))

    @staticmethod
    @requires_feature(FeatureFlag.EVENT_INFO)
    async def list_articles(user: Optional[User] = None) -> list[ContentArticle]:
        """This community's articles, minus any this reader may not see."""
        slug = await EventInfoService._tenant_slug()
        live = await FeatureFlagService().enabled_flags()
        roles = await EventInfoService._reader_roles(user)
        return [
            article for article in articles_for_tenant(slug)
            if EventInfoService._readable(article, live, roles)
        ]

    @staticmethod
    @requires_feature(FeatureFlag.EVENT_INFO)
    async def get_article(slug: str, user: Optional[User] = None) -> Optional[ContentArticle]:
        """One article by slug, or ``None`` when it is missing or not for this reader.

        Same answer for "no such article", "gated off" and "not your role", for
        the reason ``HelpService`` gives: a reader who followed a stale link
        should not learn which optional features their community has turned off,
        nor which articles exist for people with more access than them.
        """
        article = article_for_tenant(await EventInfoService._tenant_slug(), slug)
        if article is None:
            return None
        live = await FeatureFlagService().enabled_flags()
        roles = await EventInfoService._reader_roles(user)
        return article if EventInfoService._readable(article, live, roles) else None

    @staticmethod
    @requires_feature(FeatureFlag.EVENT_INFO)
    async def get_snippet(name: str, user: Optional[User] = None) -> Optional[ContentSnippet]:
        """One popup snippet, or ``None`` when its article is not for this reader.

        The gate is the owning article's, not the snippet's: a snippet is a
        region of an article, so it can never be more readable than the article
        it was cut from.
        """
        slug = await EventInfoService._tenant_slug()
        snippet = snippet_for_tenant(slug, name)
        if snippet is None:
            return None
        article = article_for_tenant(slug, snippet.article_slug)
        if article is None:
            return None
        live = await FeatureFlagService().enabled_flags()
        roles = await EventInfoService._reader_roles(user)
        return snippet if EventInfoService._readable(article, live, roles) else None
