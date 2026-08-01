"""In-app help content: the shipped articles documenting how the app works.

A peer of ``application/services`` rather than a service itself — the loading
here has no database, no tenant and no rules, and the layer hook classifies it
the same way it classifies ``application/events``. The feature-flag filtering
that decides *which* articles a community sees is a rule, so it lives in
``application.services.HelpService``.

The document model and the directory loader are shared with the per-community
event handbook and live in ``application/content``; the block and span names are
re-exported here because help's callers predate the split.

This section is **app mechanics** — how the schedule board works, what the bot
DMs you, how crew signup is approved — and is identical for every community.
Anything specific to one community's event belongs in
``application/event_info`` instead.
"""

from application.content import (
    CHIP_TONES,
    STATE_STYLES,
    Block,
    Span,
    parse_blocks,
    parse_inline,
    plain_text,
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
    'plain_text',
    'reload_articles',
    'slugify',
]
