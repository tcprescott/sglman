"""Shipped prose articles: the safe document model and the directory loader.

A peer of ``application/services`` rather than a service itself — the parsing
here has no database, no tenant and no rules, and the layer hook classifies it
the same way it classifies ``application/events``. The rules that decide *which*
articles a community sees are rules, so they live in the services that own each
section (``HelpService``, ``EventInfoService``).

Two sections build on this: ``application/help`` (how the app works, identical
everywhere) and ``application/event_info`` (one community's own event handbook).
"""

from application.content.blocks import (
    CHIP_TONES,
    STATE_STYLES,
    Block,
    Span,
    parse_blocks,
    parse_inline,
    plain_text,
    slugify,
)
from application.content.catalog import (
    ContentArticle,
    ContentCatalog,
    ContentSnippet,
    catalog_for,
    reload_all,
)

__all__ = [
    'CHIP_TONES',
    'STATE_STYLES',
    'Block',
    'ContentArticle',
    'ContentCatalog',
    'ContentSnippet',
    'Span',
    'catalog_for',
    'parse_blocks',
    'parse_inline',
    'plain_text',
    'reload_all',
    'slugify',
]
