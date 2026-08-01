"""Loading and indexing the shipped help articles.

Articles are Markdown files in ``application/help/content``. They live inside the
package rather than at the repo root because ``.dockerignore`` drops ``docs`` and
root-level ``*.md`` from the build context — help is runtime content, not project
documentation, and putting it beside the loader keeps it in the image without a
negation rule someone has to remember.

Each file carries a small front-matter header and, optionally, one or more named
``:::snippet`` regions. A snippet is not a second copy of the text: it marks a
span of the article that a popup elsewhere in the app also shows, so the popup
and the article cannot drift. Popups deep-link back to the heading the snippet
sits under.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from application.help.blocks import Block, parse_blocks, plain_text
from models import FeatureFlag

logger = logging.getLogger(__name__)

__all__ = [
    'HelpArticle',
    'HelpSnippet',
    'all_articles',
    'get_article',
    'get_snippet',
    'reload_articles',
]

CONTENT_DIR = Path(__file__).parent / 'content'

_FRONT_MATTER_RE = re.compile(r'^---\s*\n(?P<body>.*?)\n---\s*\n', re.DOTALL)
_SNIPPET_OPEN_RE = re.compile(r'^:::snippet\s+(?P<name>[a-z0-9-]+)\s*$')
_SNIPPET_CLOSE = ':::'


@dataclass(frozen=True)
class HelpSnippet:
    """A named region of an article, rendered inline in a popup.

    ``anchor`` is the heading the region sits under, so "Read more" lands on the
    part of the article the popup was quoting rather than the top of the page.
    """

    name: str
    article_slug: str
    article_title: str
    anchor: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class HelpArticle:
    slug: str
    title: str
    summary: str
    icon: str
    order: int
    feature: FeatureFlag | None
    blocks: tuple[Block, ...]
    snippets: dict[str, HelpSnippet]
    search_text: str

    @property
    def headings(self) -> list[tuple[str, str]]:
        """``(anchor, text)`` for each top-level heading — the in-article nav."""
        return [
            (block.anchor, ''.join(span.text for span in block.spans))
            for block in self.blocks
            if block.kind == 'heading' and block.level == 2
        ]


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group('body').splitlines():
        key, _, value = line.partition(':')
        if _:
            meta[key.strip()] = value.strip()
    return meta, text[match.end():]


def _resolve_feature(raw: str) -> FeatureFlag | None:
    """Map a front-matter ``feature:`` name to its flag, or ``None``.

    An unknown name is logged and treated as ungated rather than raising: a typo
    in an article header must not take the help page down, and the failure mode
    that hides an article silently is the harder one to notice.
    """
    if not raw:
        return None
    try:
        return FeatureFlag[raw.upper()]
    except KeyError:
        logger.warning('help article names unknown feature flag %r; treating as ungated', raw)
        return None


def _split_snippets(body: str) -> tuple[str, dict[str, tuple[int, int]]]:
    """Strip the ``:::snippet`` markers, returning the body and line ranges.

    The markers are removed so the region renders as ordinary article content;
    the ranges are recorded against the *stripped* line numbering so a snippet
    can be re-parsed from exactly the lines the article shows.
    """
    kept: list[str] = []
    ranges: dict[str, tuple[int, int]] = {}
    open_name: str | None = None
    open_at = 0
    for line in body.splitlines():
        opening = _SNIPPET_OPEN_RE.match(line.strip())
        if opening:
            if open_name is not None:
                logger.warning('help snippet %r opened inside %r; ignoring', opening.group('name'), open_name)
                continue
            open_name = opening.group('name')
            open_at = len(kept)
            continue
        if line.strip() == _SNIPPET_CLOSE and open_name is not None:
            ranges[open_name] = (open_at, len(kept))
            open_name = None
            continue
        kept.append(line)
    if open_name is not None:
        logger.warning('help snippet %r never closed; taking it to end of article', open_name)
        ranges[open_name] = (open_at, len(kept))
    return '\n'.join(kept), ranges


def _anchor_before(lines: list[str], start: int) -> str:
    """The slug of the nearest heading at or above ``start``."""
    from application.help.blocks import slugify

    for index in range(min(start, len(lines)) - 1, -1, -1):
        heading = re.match(r'^#{2,4}\s+(.*)$', lines[index].strip())
        if heading:
            return slugify(re.sub(r'[*`]', '', heading.group(1).strip()))
    return ''


def _load_article(path: Path) -> HelpArticle | None:
    try:
        raw = path.read_text(encoding='utf-8')
    except OSError:
        logger.exception('could not read help article %s', path)
        return None

    meta, body = _parse_front_matter(raw)
    stripped, ranges = _split_snippets(body)
    lines = stripped.splitlines()
    blocks = parse_blocks(stripped)
    slug = meta.get('slug') or path.stem
    title = meta.get('title') or slug.replace('-', ' ').capitalize()

    snippets = {
        name: HelpSnippet(
            name=name,
            article_slug=slug,
            article_title=title,
            anchor=_anchor_before(lines, start),
            blocks=tuple(parse_blocks('\n'.join(lines[start:end]))),
        )
        for name, (start, end) in ranges.items()
    }

    try:
        order = int(meta.get('order', '100'))
    except ValueError:
        order = 100

    return HelpArticle(
        slug=slug,
        title=title,
        summary=meta.get('summary', ''),
        icon=meta.get('icon', 'help_outline'),
        order=order,
        feature=_resolve_feature(meta.get('feature', '')),
        blocks=tuple(blocks),
        snippets=snippets,
        search_text=' '.join([title, meta.get('summary', ''), plain_text(blocks)]).lower(),
    )


_cache: list[HelpArticle] | None = None
_snippet_index: dict[str, HelpSnippet] | None = None


def reload_articles() -> None:
    """Drop the parsed-article cache. Used by tests and by a dev reload."""
    global _cache, _snippet_index
    _cache = None
    _snippet_index = None


def all_articles() -> list[HelpArticle]:
    """Every shipped article, ordered for display. Parsed once per process."""
    global _cache, _snippet_index
    if _cache is None:
        articles = [
            article
            for path in sorted(CONTENT_DIR.glob('*.md'))
            if (article := _load_article(path)) is not None
        ]
        articles.sort(key=lambda a: (a.order, a.title))
        index: dict[str, HelpSnippet] = {}
        for article in articles:
            for name, snippet in article.snippets.items():
                if name in index:
                    logger.warning(
                        'duplicate help snippet %r in %s and %s; keeping the first',
                        name, index[name].article_slug, article.slug,
                    )
                    continue
                index[name] = snippet
        _cache = articles
        _snippet_index = index
    return list(_cache)


def get_article(slug: str) -> HelpArticle | None:
    return next((article for article in all_articles() if article.slug == slug), None)


def get_snippet(name: str) -> HelpSnippet | None:
    """Look up a snippet by its global name. ``None`` when no article defines it."""
    all_articles()
    return (_snippet_index or {}).get(name)
