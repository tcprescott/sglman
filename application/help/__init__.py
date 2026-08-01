"""In-app help content: the shipped articles and the safe document model.

A peer of ``application/services`` rather than a service itself — the parsing
here has no database, no tenant and no rules, and the layer hook classifies it
the same way it classifies ``application/events``. The feature-flag filtering
that decides *which* articles a community sees is a rule, so it lives in
``application.services.HelpService``.
"""

from application.help.blocks import (
    CHIP_TONES,
    STATE_STYLES,
    Block,
    Span,
    parse_blocks,
    parse_inline,
    slugify,
)
from application.help.catalog import (
    HelpArticle,
    HelpSnippet,
    all_articles,
    get_article,
    get_snippet,
    reload_articles,
)

__all__ = [
    'CHIP_TONES',
    'STATE_STYLES',
    'Block',
    'HelpArticle',
    'HelpSnippet',
    'Span',
    'all_articles',
    'get_article',
    'get_snippet',
    'parse_blocks',
    'parse_inline',
    'reload_articles',
    'slugify',
]
