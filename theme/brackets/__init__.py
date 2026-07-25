"""Shared bracket renderer — the redesigned tournament bracket view.

A pure layout walker (:mod:`.layout`) turns a persisted ``BracketMatch`` graph
into absolute-positioned geometry + elbow connectors; the card layer
(:mod:`.cards`) paints it as interactive NiceGUI elements themed by
``static/css/brackets.css``. Consumed by the public bracket page and the admin
Results dialog. See docs/plans/bracket-ui-plan.md.
"""

from .cards import (
    BracketContext,
    render_match_card,
    render_mobile_card,
    render_section,
)
from .dialog import build_match_dialog
from .live import register_bracket_view
from .render import (
    build_context,
    detect_finals,
    entry_records,
    match_nodes,
    render_elimination,
    render_elimination_mobile,
)
from .layout import (
    CARD_HEIGHT,
    COL_WIDTH,
    GUTTER,
    MatchNode,
    Placement,
    SectionLayout,
    SlotSource,
    assign_match_numbers,
    layout_section,
    round_label,
    slot_sources,
)

__all__ = [
    'BracketContext',
    'render_match_card',
    'render_mobile_card',
    'render_section',
    'render_elimination',
    'render_elimination_mobile',
    'build_context',
    'build_match_dialog',
    'detect_finals',
    'entry_records',
    'match_nodes',
    'register_bracket_view',
    'MatchNode',
    'Placement',
    'SectionLayout',
    'SlotSource',
    'layout_section',
    'assign_match_numbers',
    'slot_sources',
    'round_label',
    'CARD_HEIGHT',
    'COL_WIDTH',
    'GUTTER',
]
