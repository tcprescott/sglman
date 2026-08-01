"""Which help articles this community's readers should see.

The articles themselves are static files (``application/help``); the one rule
worth a service is that an article documenting an optional subsystem must not be
offered to a community that has the subsystem switched off. Someone reading
"open the Volunteer tab" and finding no Volunteer tab is worse served than
someone who never saw the article — help that describes a surface the reader
cannot reach reads as a bug in the app.

Read-only and stateless; no repository, because there is no stored help.
"""

from __future__ import annotations

from application.help import HelpArticle, HelpSnippet, all_articles, get_article, get_snippet
from application.services.feature_flag_service import FeatureFlagService

__all__ = ['HelpService']


class HelpService:
    """Feature-aware access to the shipped help articles."""

    @staticmethod
    async def list_articles() -> list[HelpArticle]:
        """Every article whose feature (if any) is live for this community."""
        live = await FeatureFlagService().enabled_flags()
        return [
            article for article in all_articles()
            if article.feature is None or article.feature in live
        ]

    @staticmethod
    async def get_article(slug: str) -> HelpArticle | None:
        """One article by slug, or ``None`` when it is missing or not live here.

        Same answer for "no such article" and "gated off": a reader who followed
        a stale link should not learn which optional features their community
        has turned off.
        """
        article = get_article(slug)
        if article is None:
            return None
        if article.feature is not None:
            if article.feature not in await FeatureFlagService().enabled_flags():
                return None
        return article

    @staticmethod
    async def get_snippet(name: str) -> HelpSnippet | None:
        """One popup snippet, or ``None`` when its article is not live here.

        A caller that gets ``None`` renders no help icon at all — an icon that
        opens an empty popup is worse than no icon.
        """
        snippet = get_snippet(name)
        if snippet is None:
            return None
        article = get_article(snippet.article_slug)
        if article is not None and article.feature is not None:
            if article.feature not in await FeatureFlagService().enabled_flags():
                return None
        return snippet

    @staticmethod
    async def search(query: str) -> list[HelpArticle]:
        """Articles matching every whitespace-separated term, in catalogue order.

        Deliberately an AND over terms rather than a ranked relevance score:
        eight articles do not need ranking, and "crew withdraw" finding only the
        article that mentions both is the behaviour someone typing two words
        expects.
        """
        articles = await HelpService.list_articles()
        terms = [term for term in query.lower().split() if term]
        if not terms:
            return articles
        return [
            article for article in articles
            if all(term in article.search_text for term in terms)
        ]
