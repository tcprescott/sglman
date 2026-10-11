"""Which help articles this community's readers should see.

The articles themselves are static files (``application/help``); the one rule
worth a service is that an article documenting an optional subsystem must not be
offered to a community that has the subsystem switched off. Someone reading
"open the Volunteer tab" and finding no Volunteer tab is worse served than
someone who never saw the article — help that describes a surface the reader
cannot reach reads as a bug in the app.

The second rule is the reader. An article with ``audience: staff`` documents the
admin surfaces and is offered only to someone who can open Admin here; an
article naming ``roles:`` only to someone holding one of them. Either way the
article is invisible to everyone else — listed nowhere, not found by search, and
"does not exist" by URL — which is why ``/help`` can stay a public page.

Read-only and stateless; no repository, because there is no stored help.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from application.content import (
    AUDIENCE_EVERYONE,
    AUDIENCE_STAFF,
    Block,
    article_sections,
    link_filter,
    prune_links,
)
from application.help import HelpArticle, HelpSnippet, all_articles, get_article, get_snippet
from application.services.auth_service import AuthService
from application.services.feature_flag_service import FeatureFlagService
from models import FeatureFlag, Role, User

__all__ = ['HelpService']


@dataclass(frozen=True)
class _Reader:
    staff: bool = False
    super_admin: bool = False
    roles: frozenset[Role] = frozenset()


_ANONYMOUS = _Reader()


def _is_gated(article: HelpArticle) -> bool:
    return article.audience != AUDIENCE_EVERYONE or bool(article.roles)


class HelpService:
    """Feature- and reader-aware access to the shipped help articles."""

    @staticmethod
    def for_staff(article: HelpArticle) -> bool:
        """Whether ``article`` belongs in the "For staff" group.

        Any article gated by reader: ``audience: staff`` (anyone who can open
        Admin, tournament admins and crew coordinators included) or a
        ``roles:`` list (only holders of one of them).
        """
        return _is_gated(article)

    @staticmethod
    async def _reader(user: Optional[User]) -> _Reader:
        """Who is reading, as far as the article gates care.

        Costs nothing while no shipped article is gated by reader, which keeps
        the public pages free of role queries for everyone.
        """
        if user is None or not any(_is_gated(a) for a in all_articles()):
            return _ANONYMOUS
        super_admin = await AuthService.is_super_admin(user)
        return _Reader(
            staff=super_admin or await AuthService.can_view_admin(user),
            super_admin=super_admin,
            roles=frozenset(await AuthService.get_roles(user)),
        )

    @staticmethod
    def _readable(article: HelpArticle, live: set, reader: _Reader) -> bool:
        if article.feature is not None and article.feature not in live:
            return False
        if article.audience == AUDIENCE_STAFF and not reader.staff:
            return False
        if article.roles and not (reader.super_admin or reader.roles.intersection(article.roles)):
            return False
        return True

    @staticmethod
    async def prune_links(blocks, user: Optional[User] = None) -> tuple[Block, ...]:
        """``blocks`` without the article links this reader could not follow, here.

        Articles link to each other without knowing which community they are
        read in, so a link to a gated article (``volunteering`` where volunteers
        are off, a role-gated handbook page for a signed-out reader) lands on
        "does not exist". The article and snippet getters here and in
        ``EventInfoService`` run their blocks through this before handing them
        out, so a link that would dead-end is never offered. Only the sections
        the blocks actually link into are looked up — a help icon's snippet
        with no links costs nothing.
        """
        sections = article_sections(blocks)
        if not sections:
            return tuple(blocks)
        help_slugs: set[str] = set()
        if '/help' in sections:
            help_slugs = {article.slug for article in await HelpService.list_articles(user)}
        event_slugs = None
        if '/event-info' in sections and await FeatureFlagService().is_enabled(FeatureFlag.EVENT_INFO):
            from application.services.event_info_service import EventInfoService

            event_slugs = {a.slug for a in await EventInfoService.list_articles(user)}
        return prune_links(blocks, link_filter(help_slugs, event_slugs))

    @staticmethod
    async def list_articles(user: Optional[User] = None) -> list[HelpArticle]:
        """Every article this reader may open here, the "For staff" group last.

        An article is offered when its feature (if any) is live for this
        community and the reader passes its ``audience`` and ``roles`` gates.
        """
        live = await FeatureFlagService().enabled_flags()
        reader = await HelpService._reader(user)
        readable = [a for a in all_articles() if HelpService._readable(a, live, reader)]
        return (
            [a for a in readable if not HelpService.for_staff(a)]
            + [a for a in readable if HelpService.for_staff(a)]
        )

    @staticmethod
    async def get_article(slug: str, user: Optional[User] = None) -> HelpArticle | None:
        """One article by slug, or ``None`` when it is missing or not live here.

        Same answer for "no such article", "gated off" and "not for you": a
        reader who followed a stale link should not learn which optional
        features their community has turned off, nor which articles exist for
        people with more access than them. Links to articles this reader cannot
        open are pruned (:meth:`prune_links`).
        """
        article = get_article(slug)
        if article is None:
            return None
        live = await FeatureFlagService().enabled_flags()
        if not HelpService._readable(article, live, await HelpService._reader(user)):
            return None
        return replace(article, blocks=await HelpService.prune_links(article.blocks, user))

    @staticmethod
    async def get_snippet(name: str, user: Optional[User] = None) -> HelpSnippet | None:
        """One popup snippet, or ``None`` when its article is not live here.

        A caller that gets ``None`` renders no help icon at all — an icon that
        opens an empty popup is worse than no icon. The gate is the owning
        article's: a snippet is never more readable than the article it is cut
        from.
        """
        snippet = get_snippet(name)
        if snippet is None:
            return None
        article = get_article(snippet.article_slug)
        if article is not None:
            live = await FeatureFlagService().enabled_flags()
            if not HelpService._readable(article, live, await HelpService._reader(user)):
                return None
        return replace(snippet, blocks=await HelpService.prune_links(snippet.blocks, user))

    @staticmethod
    async def search(query: str, user: Optional[User] = None) -> list[HelpArticle]:
        """Articles matching every whitespace-separated term, in catalogue order.

        Deliberately an AND over terms rather than a ranked relevance score:
        a dozen articles do not need ranking, and "crew withdraw" finding only the
        article that mentions both is the behaviour someone typing two words
        expects.
        """
        articles = await HelpService.list_articles(user)
        terms = [term for term in query.lower().split() if term]
        if not terms:
            return articles
        return [
            article for article in articles
            if all(term in article.search_text for term in terms)
        ]
