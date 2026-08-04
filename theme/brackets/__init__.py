"""Shared bracket renderer — the redesigned tournament bracket view.

A pure layout walker (:mod:`.layout`) turns a persisted ``BracketMatch`` graph
into absolute-positioned geometry + elbow connectors; the card layer
(:mod:`.cards`) paints it as interactive NiceGUI elements themed by
``static/css/brackets.css``. Consumed by the public bracket page and the admin
Results dialog. See docs/features/brackets.md.
"""

from .cards import (
    BracketContext,
    render_match_card,
    render_mobile_card,
    render_section,
)
from .dialog import build_match_dialog
from .labels import (
    FORMAT_LABELS,
    FORMAT_OPTIONS,
    STATE_COLORS,
    STATE_LABELS,
    config_summary,
    format_label,
    stage_label,
    state_color,
    state_label,
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
from .live import register_bracket_view
from .render import (
    build_context,
    detect_finals,
    entry_avatars,
    entry_records,
    match_nodes,
    render_elimination,
    render_elimination_mobile,
    results_from_matches,
)
from .visibility import is_visible, visible_stages

__all__ = [
    'CARD_HEIGHT',
    'COL_WIDTH',
    'FORMAT_LABELS',
    'FORMAT_OPTIONS',
    'GUTTER',
    'STATE_COLORS',
    'STATE_LABELS',
    'BracketContext',
    'MatchNode',
    'Placement',
    'SectionLayout',
    'SlotSource',
    'assign_match_numbers',
    'build_context',
    'build_match_dialog',
    'config_summary',
    'detect_finals',
    'entry_avatars',
    'entry_records',
    'format_label',
    'is_visible',
    'layout_section',
    'match_nodes',
    'register_bracket_view',
    'render_elimination',
    'render_elimination_mobile',
    'render_match_card',
    'render_mobile_card',
    'render_section',
    'results_from_matches',
    'round_label',
    'slot_sources',
    'stage_label',
    'state_color',
    'state_label',
    'visible_stages',
]
