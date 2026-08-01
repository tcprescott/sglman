"""Rendering parsed help blocks with native NiceGUI elements.

There is deliberately no ``ui.markdown`` here. Every block and every span is
drawn by a branch below, so an article can only ever produce elements this module
creates — the article text reaches the page as element *content*, never as
markup. That is what makes shipping editable prose through the UI safe, and it is
the same reason ``check_markdown_xss`` exists.

The vocabulary is closed: six block kinds, seven span kinds. Anything the parser
could not classify arrived here as plain text and renders as plain text.
"""

from nicegui import ui

from application.help import STATE_STYLES, Block, Span

__all__ = ['render_blocks', 'render_spans']


def _render_span(span: Span) -> None:
    if span.kind == 'link':
        # Internal links stay in this tab; anything off-site opens a new one, so
        # a reader following a link out of the help does not lose their place.
        ui.link(span.text, span.href, new_tab=not span.href.startswith(('/', '#'))) \
            .classes('wiz-help-link')
    elif span.kind == 'strong':
        ui.label(span.text).classes('wiz-help-inline text-weight-bold')
    elif span.kind == 'em':
        ui.label(span.text).classes('wiz-help-inline wiz-help-em')
    elif span.kind == 'code':
        ui.label(span.text).classes('wiz-help-inline wiz-help-code')
    elif span.kind == 'chip':
        with ui.element('span').classes(f'wiz-chip wiz-chip--{span.tone}'):
            ui.label(span.text).classes('wiz-help-inline')
    elif span.kind == 'state':
        # Drawn from the same icon and colour class the schedule board's own
        # state cell uses, so the help shows the reader the thing they will
        # actually see rather than a stylised stand-in.
        icon, tone = STATE_STYLES[span.text]
        with ui.element('span').classes('wiz-help-state'):
            ui.icon(icon).classes(tone).props('size=xs')
            ui.label(span.text).classes('wiz-help-inline')
    else:
        ui.label(span.text).classes('wiz-help-inline')


def render_spans(spans: tuple[Span, ...]) -> None:
    """Render one run of inline content into the current slot."""
    for span in spans:
        _render_span(span)


def _render_table(block: Block) -> None:
    # A hand-built table rather than ``ui.table``: the cells hold chips, icons
    # and links, which a ui.table column cannot carry without a Vue slot, and
    # these are prose tables of a handful of rows, not sortable data grids.
    # (mobile-grid: exempt — static prose, scrolls in its own container.)
    with ui.element('div').classes('wiz-help-table-wrap'):
        with ui.element('table').classes('wiz-help-table'):
            if block.headers:
                with ui.element('thead'), ui.element('tr'):
                    for cell in block.headers:
                        with ui.element('th'):
                            render_spans(cell)
            with ui.element('tbody'):
                for row in block.rows:
                    with ui.element('tr'):
                        for cell in row:
                            with ui.element('td'):
                                render_spans(cell)


def _render_list(block: Block) -> None:
    tag = 'ul' if block.kind == 'bullets' else 'ol'
    with ui.element(tag).classes('wiz-help-list'):
        for item in block.items:
            with ui.element('li'):
                render_spans(item)


def render_blocks(blocks, *, heading_offset: int = 0) -> None:
    """Render a block list into the current slot.

    ``heading_offset`` demotes every heading by that many levels — a popup
    quoting a snippet renders its headings smaller than the article does, so a
    two-line popup does not open with a page title.
    """
    for block in blocks:
        if block.kind == 'heading':
            level = min(block.level + heading_offset, 6)
            heading = ui.element(f'h{level}').classes(f'wiz-help-h{level}')
            if block.anchor and not heading_offset:
                # The anchor rides on the heading itself so /help/x#y lands on it
                # and so the in-article contents list has something to target.
                heading.props(f'id={block.anchor}')
            with heading:
                render_spans(block.spans)
        elif block.kind == 'para':
            with ui.element('p').classes('wiz-help-p'):
                render_spans(block.spans)
        elif block.kind in ('bullets', 'numbers'):
            _render_list(block)
        elif block.kind == 'table':
            _render_table(block)
        elif block.kind == 'note':
            with ui.element('aside').classes('wiz-help-note'):
                ui.icon('info').props('size=xs').classes('wiz-help-note-icon')
                with ui.element('span'):
                    render_spans(block.spans)
