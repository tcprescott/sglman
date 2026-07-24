"""Match-card + section rendering for the redesigned bracket view.

Presentation layer over :mod:`theme.brackets.layout`: it consumes the pure
placements/connectors and paints absolutely-positioned NiceGUI elements — round
headers (sticky, with best-of/time chrome), match cards (seed · avatar · name ·
score cell, winner-accented), and the elbow connectors. All colors/sizes come
from ``static/css/brackets.css`` (``--bracket-*`` custom properties); this module
only positions elements and stamps the classes/data attributes the CSS and the
hover-run script key off.

No ORM writes and no business logic — read-only ``BracketMatch`` attribute access
for display, the sanctioned presentation-layer pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from nicegui import ui

from models import BracketMatch, BracketMatchState

from .layout import (
    CARD_HEIGHT,
    COL_STRIDE,
    COL_WIDTH,
    Placement,
    SectionLayout,
    SlotSource,
    avatar_hue,
    avatar_initial,
    round_label,
)

_STATE_CLASS = {
    BracketMatchState.PENDING: 'is-pending',
    BracketMatchState.OPEN: 'is-open',
    BracketMatchState.COMPLETE: 'is-complete',
}


@dataclass
class BracketContext:
    """Everything the card layer needs to render one bracket, resolved once.

    Built by the page from the persisted graph; passed down to every section so
    the rendering stays a pure projection of these lookups.
    """

    entry_name: Dict[int, str]
    entry_seed: Dict[int, Optional[int]] = field(default_factory=dict)
    match_number: Dict[int, int] = field(default_factory=dict)
    slot_sources: Dict = field(default_factory=dict)  # (match_id, slot) -> SlotSource
    rounds_config: Dict[str, dict] = field(default_factory=dict)
    scheduled_fmt: Callable[[str], str] = str  # UTC iso -> display string
    on_card_click: Optional[Callable[[int], None]] = None


def _slot_entry_id(match: BracketMatch, slot: int) -> Optional[int]:
    return match.entry1_id if slot == 1 else match.entry2_id


def _slot_score(match: BracketMatch, slot: int) -> Optional[int]:
    return match.entry1_score if slot == 1 else match.entry2_score


def _placeholder_text(
    match: BracketMatch, slot: int, ctx: BracketContext, *, completed: bool
) -> str:
    """Label for an empty slot: BYE, a source hint, or TBD."""
    other = _slot_entry_id(match, 2 if slot == 1 else 1)
    if completed and other is not None:
        return 'BYE'
    source: Optional[SlotSource] = ctx.slot_sources.get((match.id, slot))
    if source is not None:
        num = ctx.match_number.get(source.source_match_id)
        who = 'Winner' if source.kind == 'winner' else 'Loser'
        return f'{who} of {num}' if num is not None else who
    return 'TBD'


def _render_slot(match: BracketMatch, slot: int, ctx: BracketContext) -> None:
    completed = match.state == BracketMatchState.COMPLETE
    entry_id = _slot_entry_id(match, slot)
    is_winner = completed and match.winner_id is not None and entry_id == match.winner_id
    is_loser = completed and match.winner_id is not None and entry_id != match.winner_id

    classes = 'bracket-slot'
    if entry_id is None:
        classes += ' is-empty'
    if is_winner:
        classes += ' is-winner'
    if is_loser:
        classes += ' is-loser'

    row = ui.element('div').classes(classes)
    if entry_id is not None:
        row.props(f'data-entrant-id={entry_id}')

    with row:
        seed = ctx.entry_seed.get(entry_id) if entry_id is not None else None
        # Always emit the seed cell (empty when unseeded) so the four columns
        # (seed · avatar · name · score) stay aligned across every slot.
        ui.label(str(seed) if seed is not None else '').classes('bracket-seed')

        if entry_id is not None:
            name = ctx.entry_name.get(entry_id, 'Unknown')
            _avatar(name)
            ui.label(name).classes('bracket-name').tooltip(name)
        else:
            ui.element('div').classes('bracket-avatar is-empty')
            ui.label(_placeholder_text(match, slot, ctx, completed=completed)) \
                .classes('bracket-name is-placeholder')

        # Score cell: the visual anchor. Number when scored, else a W/L glyph;
        # FF marks the forfeiting (losing) side of a walkover.
        score = _slot_score(match, slot)
        if completed and match.forfeit and is_loser:
            score_txt = 'FF'
        elif score is not None:
            score_txt = str(score)
        elif is_winner:
            score_txt = 'W'
        elif is_loser:
            score_txt = 'L'
        else:
            score_txt = ''
        ui.label(score_txt).classes('bracket-score')


def _avatar(name: str) -> None:
    ui.label(avatar_initial(name)).classes('bracket-avatar').style(
        f'--bracket-avatar-hue: {avatar_hue(name)}'
    )


def render_match_card(match: BracketMatch, placement: Placement, ctx: BracketContext) -> None:
    state_class = _STATE_CLASS.get(match.state, 'is-pending')
    card = ui.element('div').classes(f'bracket-match {state_class}').style(
        f'left: {placement.left}px; top: {placement.top}px; '
        f'width: {COL_WIDTH}px; height: {CARD_HEIGHT}px'
    )
    card.props(f'data-match-id={match.id}')

    number = ctx.match_number.get(match.id)
    with card:
        if number is not None:
            ui.label(str(number)).classes('bracket-match-num')
        _render_slot(match, 1, ctx)
        _render_slot(match, 2, ctx)

    if ctx.on_card_click is not None:
        card.classes('is-clickable')
        card.on('click', lambda _=None, mid=match.id: ctx.on_card_click(mid))


def render_mobile_card(match: BracketMatch, ctx: BracketContext) -> None:
    """The same match card in normal flow (full-width) for the mobile accordion."""
    state_class = _STATE_CLASS.get(match.state, 'is-pending')
    card = ui.element('div').classes(f'bracket-match bracket-match-flow {state_class}')
    card.props(f'data-match-id={match.id}')
    number = ctx.match_number.get(match.id)
    with card:
        if number is not None:
            ui.label(str(number)).classes('bracket-match-num')
        _render_slot(match, 1, ctx)
        _render_slot(match, 2, ctx)
    if ctx.on_card_click is not None:
        card.classes('is-clickable')
        card.on('click', lambda _=None, mid=match.id: ctx.on_card_click(mid))


def _render_header(
    col: int,
    round_number: int,
    ctx: BracketContext,
    *,
    is_grand_final: bool,
    is_reset: bool,
    max_winners_round: Optional[int],
    max_losers_magnitude: Optional[int],
) -> None:
    with ui.element('div').classes('bracket-header'):
        ui.label(
            round_label(
                round_number,
                is_grand_final=is_grand_final,
                is_reset=is_reset,
                max_winners_round=max_winners_round,
                max_losers_magnitude=max_losers_magnitude,
            )
        ).classes('bracket-header-name')
        meta = ctx.rounds_config.get(str(round_number)) or {}
        with ui.row().classes('bracket-header-meta'):
            scheduled = meta.get('scheduled_at')
            if scheduled:
                ui.label(ctx.scheduled_fmt(scheduled)).classes('bracket-header-time')
            best_of = meta.get('best_of')
            if best_of:
                ui.label(f'Best of {best_of}').classes('bracket-badge')


def render_section(
    title: Optional[str],
    layout: SectionLayout,
    matches_by_id: Dict[int, BracketMatch],
    ctx: BracketContext,
    *,
    gf_round: Optional[int] = None,
    reset_round: Optional[int] = None,
    max_winners_round: Optional[int] = None,
    max_losers_magnitude: Optional[int] = None,
) -> None:
    """Render one bracket section (winners+finals, or losers) end to end."""
    if not layout.placements:
        return
    if title:
        ui.label(title).classes('bracket-section-title')

    with ui.element('div').classes('bracket-scroll'):
        with ui.element('div').classes('bracket-headers').style(f'width: {layout.width}px'):
            for col, round_number in enumerate(layout.columns):
                _render_header(
                    col, round_number, ctx,
                    is_grand_final=(gf_round is not None and round_number == gf_round),
                    is_reset=(reset_round is not None and round_number == reset_round),
                    max_winners_round=max_winners_round,
                    max_losers_magnitude=max_losers_magnitude,
                )
        with ui.element('div').classes('bracket-canvas').style(
            f'width: {layout.width}px; height: {layout.height}px'
        ):
            for seg in layout.connectors:
                if seg.orientation == 'h':
                    ui.element('div').classes('bracket-line bracket-line-h').style(
                        f'left: {seg.x}px; top: {seg.y}px; width: {max(seg.length, 0)}px'
                    )
                else:
                    ui.element('div').classes('bracket-line bracket-line-v').style(
                        f'left: {seg.x}px; top: {seg.y}px; height: {max(seg.length, 0)}px'
                    )
            for match_id, placement in layout.placements.items():
                match = matches_by_id.get(match_id)
                if match is not None:
                    render_match_card(match, placement, ctx)
