"""Parsing ``changelog.md`` into dated entries.

Each entry opens with a level-two heading carrying an ISO 8601 date interval and
a title — ``## 2026-10-05/2026-10-11 Event check-in`` — and runs to the next one.
The interval is calendar dates, not instants, so there is no timezone to apply.
A heading that does not match is logged and its section dropped rather than
raised: a typo in the file must not take the page down. ``test_changelog``
fails the build on the same typo, so it never reaches a reader.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from application.content import Block, parse_blocks

logger = logging.getLogger(__name__)

__all__ = ['ChangelogEntry', 'all_entries', 'parse_changelog', 'reload_entries']

CHANGELOG_PATH = Path(__file__).parent / 'changelog.md'

ENTRY_HEADING_RE = re.compile(
    r'^## (?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2}) (?P<title>\S.*?)\s*$'
)


@dataclass(frozen=True)
class ChangelogEntry:
    start: date
    end: date
    title: str
    blocks: tuple[Block, ...]

    @property
    def anchor(self) -> str:
        return self.start.isoformat()

    @property
    def period(self) -> str:
        """``Oct 5 – 11, 2026``, widening only as far as the interval needs."""
        start, end = self.start, self.end
        if start == end:
            return f'{start:%b} {start.day}, {start.year}'
        if start.year != end.year:
            return f'{start:%b} {start.day}, {start.year} – {end:%b} {end.day}, {end.year}'
        if start.month != end.month:
            return f'{start:%b} {start.day} – {end:%b} {end.day}, {end.year}'
        return f'{start:%b} {start.day} – {end.day}, {end.year}'


def _entry(heading: str, body: list[str]) -> ChangelogEntry | None:
    match = ENTRY_HEADING_RE.match(heading)
    if match is None:
        logger.warning('changelog: unrecognised entry heading %r; section skipped', heading)
        return None
    try:
        start = date.fromisoformat(match['start'])
        end = date.fromisoformat(match['end'])
    except ValueError:
        logger.warning('changelog: invalid date in heading %r; section skipped', heading)
        return None
    if end < start:
        logger.warning('changelog: heading %r ends before it starts; section skipped', heading)
        return None
    return ChangelogEntry(
        start=start,
        end=end,
        title=match['title'],
        blocks=tuple(parse_blocks('\n'.join(body))),
    )


def parse_changelog(text: str) -> list[ChangelogEntry]:
    """Every well-formed entry in ``text``, newest first."""
    entries: list[ChangelogEntry] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith('## '):
            if heading is not None and (entry := _entry(heading, body)):
                entries.append(entry)
            heading, body = line.rstrip(), []
        elif heading is not None:
            body.append(line)
    if heading is not None and (entry := _entry(heading, body)):
        entries.append(entry)
    return sorted(entries, key=lambda e: e.start, reverse=True)


@lru_cache(maxsize=1)
def _load() -> tuple[ChangelogEntry, ...]:
    return tuple(parse_changelog(CHANGELOG_PATH.read_text(encoding='utf-8')))


def all_entries() -> list[ChangelogEntry]:
    """Every shipped entry, newest first. Parsed once per process."""
    return list(_load())


def reload_entries() -> None:
    """Drop the parse cache. Used by tests and by a dev reload."""
    _load.cache_clear()
