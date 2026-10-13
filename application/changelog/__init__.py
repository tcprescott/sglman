"""The in-app changelog: what changed in Wizzrobe, roughly a week per entry.

A peer of ``application/help``: shipped prose with no database, no tenant and no
rules, parsed into the same safe block model (``application/content``) and never
handed to ``ui.markdown``. The entries live in ``changelog.md`` and ``changes/``
beside this module so they ride into the image; ``.dockerignore`` drops
root-level ``*.md``.
"""

from application.changelog.catalog import (
    CATEGORIES,
    UNSORTED,
    ChangelogEntry,
    ChangelogSection,
    all_entries,
    parse_changelog,
    reload_entries,
)

__all__ = [
    'CATEGORIES',
    'UNSORTED',
    'ChangelogEntry',
    'ChangelogSection',
    'all_entries',
    'parse_changelog',
    'reload_entries',
]
