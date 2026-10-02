"""The safe document model shipped prose articles are parsed into.

Shared by the two article sections — in-app help (``application/help``) and the
per-community event handbook (``application/event_info``). Both are authored as
Markdown, and neither is **ever** handed to ``ui.markdown``. NiceGUI's markdown
and html elements pass raw HTML straight through, so rendering a file's text
through them is the same stored-XSS shape
``check_markdown_xss`` exists to stop — the fact that these particular files are
developer-authored and version-controlled is a property of today's workflow, not
of the renderer. Parsing to a closed set of blocks and spans and rendering each
one with a native element makes the surface safe by construction: there is no
path from article text to markup, so an article can never emit an element the
renderer does not itself create.

The subset is deliberately small — headings, paragraphs, lists, tables, notes,
and seven inline forms. Anything unrecognised degrades to plain text rather than
raising, because a malformed article should read badly, not 500 the page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Callable

__all__ = [
    'Block',
    'Span',
    'article_sections',
    'internal_target',
    'link_filter',
    'parse_blocks',
    'parse_inline',
    'plain_text',
    'prune_links',
    'slugify',
]

# Inline forms, matched in one pass so a later form cannot be found inside an
# earlier one's text (a link label containing ** stays literal).
_INLINE_RE = re.compile(
    # Bold before italic: the alternation is ordered, so `**x**` must be offered
    # first or the single-asterisk branch claims its opening pair.
    r'\*\*(?P<strong>[^*]+?)\*\*'
    r'|\*(?P<em>[^*\n]+?)\*'
    r'|`(?P<code>[^`]+?)`'
    r'|\[(?P<link_text>[^\]]+?)\]\((?P<href>[^)\s]+?)\)'
    # Colon-delimited, not pipe-delimited: chips are most useful inside the
    # tables that explain what each state means, and a literal `|` there would
    # split the cell it is describing.
    r'|\{chip:(?P<chip_tone>[a-z-]+):(?P<chip_text>[^}]+?)\}'
    r'|\{state:(?P<state_text>[^}]+?)\}'
)

# Link targets we will render as links. Everything else renders as plain text —
# `javascript:` and `data:` URIs above all, but also anything unparseable.
_SAFE_HREF_RE = re.compile(r'^(?:/[^\s]*|#[^\s]*|https://[^\s]+|mailto:[^\s]+)$')

# The six chip tones static/css/styles.css defines. An article naming any other
# falls back to neutral rather than emitting a class with no rule behind it.
CHIP_TONES = frozenset({'ok', 'pending', 'live', 'neutral', 'cancelled', 'candidate'})

# The five match states the schedule board actually shows a player or crew
# member, mapped to the icon and colour class the board's own state cell uses
# (theme/tables/match_slots.py). Help that draws its own chip in its own colours
# teaches a vocabulary the board does not speak.
STATE_STYLES: dict[str, tuple[str, str]] = {
    'Scheduled': ('schedule', 'st-neutral'),
    'Checked In': ('check', 'st-neutral'),
    'Started': ('play_arrow', 'st-live'),
    'Finished': ('flag', 'st-pending'),
    'Confirmed': ('verified', 'st-ok'),
}


@dataclass(frozen=True)
class Span:
    """One inline run of text.

    ``kind`` is one of ``text``, ``strong``, ``em``, ``code``, ``link``,
    ``chip``, ``state``. ``href`` is set only for links and is already known
    safe; ``tone`` only for chips.
    """

    kind: str
    text: str
    href: str = ''
    tone: str = ''


@dataclass(frozen=True)
class Block:
    """One block-level element.

    ``kind`` is one of ``heading``, ``para``, ``bullets``, ``numbers``,
    ``table``, ``note``.
    """

    kind: str
    spans: tuple[Span, ...] = ()
    items: tuple[tuple[Span, ...], ...] = ()
    rows: tuple[tuple[tuple[Span, ...], ...], ...] = ()
    headers: tuple[tuple[Span, ...], ...] = ()
    level: int = 2
    anchor: str = ''


@dataclass
class _Cursor:
    """Mutable parse state, so the block handlers can share one line pointer."""

    lines: list[str]
    index: int = 0
    blocks: list[Block] = field(default_factory=list)

    def peek(self) -> str | None:
        return self.lines[self.index] if self.index < len(self.lines) else None


def slugify(text: str) -> str:
    """A URL fragment for a heading — the same shape as ``theme.base.tab_slug``."""
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def _safe_href(href: str) -> str:
    """Return ``href`` if we will render it as a link, else ``''``."""
    return href if _SAFE_HREF_RE.match(href) else ''


def parse_inline(text: str) -> tuple[Span, ...]:
    """Split one line of article text into spans.

    Unrecognised syntax stays literal: a stray ``**`` or an unsafe link target
    renders as the characters the author typed, which is a visible defect in the
    article rather than a silent one in the page.
    """
    spans: list[Span] = []
    position = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > position:
            spans.append(Span('text', text[position:match.start()]))
        position = match.end()
        groups = match.groupdict()
        if groups['strong'] is not None:
            spans.append(Span('strong', groups['strong']))
        elif groups['em'] is not None:
            spans.append(Span('em', groups['em']))
        elif groups['code'] is not None:
            spans.append(Span('code', groups['code']))
        elif groups['link_text'] is not None:
            href = _safe_href(groups['href'] or '')
            # A rejected target keeps the label readable rather than vanishing.
            spans.append(
                Span('link', groups['link_text'], href=href) if href
                else Span('text', groups['link_text'])
            )
        elif groups['chip_text'] is not None:
            tone = groups['chip_tone'] or 'neutral'
            spans.append(Span(
                'chip', groups['chip_text'],
                tone=tone if tone in CHIP_TONES else 'neutral',
            ))
        elif groups['state_text'] is not None:
            label = groups['state_text'].strip()
            # An unknown state name is an authoring error; render the words so
            # the article still reads, without inventing an icon for it.
            spans.append(
                Span('state', label) if label in STATE_STYLES else Span('text', label)
            )
    if position < len(text):
        spans.append(Span('text', text[position:]))
    return tuple(spans)


def _split_table_row(line: str) -> list[str]:
    cells = line.strip().strip('|').split('|')
    return [cell.strip() for cell in cells]


def _is_table_divider(line: str) -> bool:
    return bool(re.match(r'^\s*\|[\s:|-]+\|\s*$', line)) and '-' in line


def _take_heading(cursor: _Cursor, line: str) -> bool:
    match = re.match(r'^(#{2,4})\s+(.*)$', line)
    if not match:
        return False
    text = match.group(2).strip()
    cursor.blocks.append(Block(
        'heading',
        spans=parse_inline(text),
        level=len(match.group(1)),
        anchor=slugify(re.sub(r'[*`]', '', text)),
    ))
    cursor.index += 1
    return True


_BULLET_RE = re.compile(r'^[-*]\s+(.*)$')
_NUMBER_RE = re.compile(r'^\d+\.\s+(.*)$')


def _take_list(cursor: _Cursor, line: str) -> bool:
    bulleted = _BULLET_RE.match(line)
    if not (bulleted or _NUMBER_RE.match(line)):
        return False
    kind = 'bullets' if bulleted else 'numbers'
    pattern = _BULLET_RE if bulleted else _NUMBER_RE
    parts: list[list[str]] = []
    while (current := cursor.peek()) is not None:
        item = pattern.match(current.strip())
        if item:
            parts.append([item.group(1).strip()])
            cursor.index += 1
            continue
        # A wrapped item: an indented, non-blank line that starts no new block
        # belongs to the item above it. Without this every hard-wrapped bullet
        # ended the list and reopened it, so a two-line item rendered as two
        # lists with a stray paragraph between them.
        if parts and current.startswith((' ', '\t')) and current.strip():
            parts[-1].append(current.strip())
            cursor.index += 1
            continue
        break
    cursor.blocks.append(Block(
        kind,
        items=tuple(parse_inline(' '.join(part)) for part in parts),
    ))
    return True


def _take_table(cursor: _Cursor, line: str) -> bool:
    following = cursor.lines[cursor.index + 1] if cursor.index + 1 < len(cursor.lines) else ''
    if not (line.strip().startswith('|') and _is_table_divider(following)):
        return False
    headers = tuple(parse_inline(cell) for cell in _split_table_row(line))
    cursor.index += 2
    rows: list[tuple[tuple[Span, ...], ...]] = []
    while (current := cursor.peek()) is not None and current.strip().startswith('|'):
        rows.append(tuple(parse_inline(cell) for cell in _split_table_row(current)))
        cursor.index += 1
    cursor.blocks.append(Block('table', headers=headers, rows=tuple(rows)))
    return True


def _take_note(cursor: _Cursor, line: str) -> bool:
    if not line.startswith('>'):
        return False
    parts: list[str] = []
    while (current := cursor.peek()) is not None and current.startswith('>'):
        parts.append(current.lstrip('>').strip())
        cursor.index += 1
    cursor.blocks.append(Block('note', spans=parse_inline(' '.join(parts).strip())))
    return True


def _take_paragraph(cursor: _Cursor) -> None:
    parts: list[str] = []
    while (current := cursor.peek()) is not None:
        stripped = current.strip()
        if not stripped or stripped.startswith(('#', '>', ':::', '|')):
            break
        if re.match(r'^[-*]\s+', stripped) or re.match(r'^\d+\.\s+', stripped):
            break
        parts.append(stripped)
        cursor.index += 1
    if parts:
        cursor.blocks.append(Block('para', spans=parse_inline(' '.join(parts))))


def parse_blocks(text: str) -> list[Block]:
    """Parse article body text into the renderable block list."""
    cursor = _Cursor(lines=text.splitlines())
    while (line := cursor.peek()) is not None:
        stripped = line.strip()
        if not stripped:
            cursor.index += 1
            continue
        if _take_heading(cursor, stripped):
            continue
        if _take_table(cursor, line):
            continue
        if _take_list(cursor, stripped):
            continue
        if _take_note(cursor, stripped):
            continue
        before = cursor.index
        _take_paragraph(cursor)
        # Belt and braces: a line no handler consumed must not spin the loop.
        if cursor.index == before:
            cursor.index += 1
    return cursor.blocks


def plain_text(blocks: list[Block]) -> str:
    """Flatten blocks to searchable text — no markup, no structure."""
    out: list[str] = []

    def add(spans: tuple[Span, ...]) -> None:
        out.extend(span.text for span in spans)

    for block in blocks:
        add(block.spans)
        for item in block.items:
            add(item)
        for header in block.headers:
            add(header)
        for row in block.rows:
            for cell in row:
                add(cell)
    return ' '.join(part.strip() for part in out if part.strip())


def internal_target(href: str) -> tuple[str, str, str] | None:
    """``(section, slug, anchor)`` for a link into an article section, else ``None``.

    ``/help/crew#approval`` is ``('/help', 'crew', 'approval')``; a section index
    (``/help``) has an empty slug. Links anywhere else — another page of the
    app, off-site, an in-page ``#anchor`` — are not article links and return
    ``None``.
    """
    path, _, anchor = href.partition('#')
    for section in ('/help', '/event-info'):
        if path == section:
            return section, '', anchor
        if path.startswith(section + '/'):
            return section, path[len(section) + 1:], anchor
    return None


def _prune_spans(spans: tuple[Span, ...], readable: Callable[[str], bool]) -> tuple[tuple[Span, ...], bool]:
    """Spans with dead links turned into their label; and whether any was dead."""
    out: list[Span] = []
    dead = False
    for span in spans:
        if span.kind == 'link' and not readable(span.href):
            out.append(Span('text', span.text))
            dead = True
        else:
            out.append(span)
    return tuple(out), dead


def prune_links(blocks, readable: Callable[[str], bool]) -> tuple[Block, ...]:
    """``blocks`` without links the reader cannot follow.

    Articles link to each other freely, but an article can be gated off (a
    feature the community has not enabled, a role the reader does not hold),
    and the link to it then lands on "does not exist". A link in running text
    keeps its words and loses the anchor. A **table row** pointing at an
    unreadable article is dropped whole: a "you are a volunteer, read this"
    row is noise in a community with no volunteers, and its label alone is a
    dead end. A table left with no rows goes too.
    """
    out: list[Block] = []
    for block in blocks:
        if block.kind == 'table':
            rows = []
            for row in block.rows:
                cells = [_prune_spans(cell, readable) for cell in row]
                if any(dead for _cell, dead in cells):
                    continue
                rows.append(tuple(cell for cell, _dead in cells))
            if rows:
                out.append(replace(block, rows=tuple(rows)))
            continue
        spans, _ = _prune_spans(block.spans, readable)
        items = tuple(_prune_spans(item, readable)[0] for item in block.items)
        out.append(replace(block, spans=spans, items=items))
    return tuple(out)


def link_filter(help_slugs, event_slugs) -> Callable[[str], bool]:
    """A ``readable(href)`` predicate for :func:`prune_links`.

    ``help_slugs`` / ``event_slugs`` are the articles this reader can open in
    each section; ``event_slugs`` is ``None`` where the community has no event
    handbook at all, which makes every ``/event-info`` link dead. Links that are
    not into an article section are always readable.
    """
    def readable(href: str) -> bool:
        target = internal_target(href)
        if target is None:
            return True
        section, slug, _anchor = target
        slugs = help_slugs if section == '/help' else event_slugs
        if slugs is None:
            return False
        return not slug or slug in slugs

    return readable


def article_sections(blocks) -> set[str]:
    """The article sections (``/help``, ``/event-info``) ``blocks`` link into."""
    sections: set[str] = set()

    def scan(spans) -> None:
        for span in spans:
            if span.kind == 'link':
                target = internal_target(span.href)
                if target is not None:
                    sections.add(target[0])

    for block in blocks:
        scan(block.spans)
        for item in block.items:
            scan(item)
        for row in block.rows:
            for cell in row:
                scan(cell)
    return sections
