"""High-level elimination rendering, shared by the public page and admin embed.

Wraps the layout walker + card layer into whole-bracket renderers (2-D connector
view + the mobile per-round accordion), plus the small pure helpers both callers
need (context assembly, finals detection, per-entry records, scheduled-time
formatting). Keeping these here — rather than in ``pages/`` — lets the admin
Results dialog embed the identical visual bracket for click-to-report
(docs/plans/bracket-ui-plan.md, U5). Presentation-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from nicegui import ui

from application.services.bracket_engines.round_names import (
    RoundNode,
    detect_finals_ids,
)
from application.services.bracket_engines.standings import ResultRow
from application.utils.timezone import format_local_display
from models import BracketMatch, BracketMatchState

from .cards import BracketContext, render_mobile_card, render_section
from .layout import (
    MatchNode,
    assign_match_numbers,
    layout_section,
    round_label,
    slot_sources,
)


def format_scheduled(iso: str) -> str:
    """A round's stored UTC ISO time → the app's Eastern display string."""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_local_display(dt)


def match_nodes(matches: List[BracketMatch]) -> List[MatchNode]:
    return [
        MatchNode(id=m.id, round=m.round, position=m.position, winner_to_id=m.winner_to_id)
        for m in matches
    ]


def detect_finals(
    matches: List[BracketMatch],
) -> Tuple[Optional[BracketMatch], Optional[BracketMatch]]:
    """Structurally locate a double-elim grand final and its optional reset.

    Thin adapter over :func:`round_names.detect_finals_ids`, which owns the
    structural rule so the Discord/service naming path and the renderer cannot
    disagree about which match is the grand final. This one maps the ids back to
    the ORM rows the caller already holds. Either may be ``None`` for an empty or
    not-yet-generated finals stage.
    """
    by_id = {m.id: m for m in matches}
    gf_id, reset_id = detect_finals_ids([
        RoundNode(
            id=m.id, round=m.round,
            winner_to_id=m.winner_to_id, loser_to_id=m.loser_to_id,
        )
        for m in matches
    ])
    return by_id.get(gf_id), by_id.get(reset_id)


def build_context(
    config: Optional[dict],
    entries,
    matches: List[BracketMatch],
    entry_name: Dict[int, str],
    *,
    on_card_click: Optional[Callable[[int], None]] = None,
    live_state: Optional[Dict[int, dict]] = None,
) -> BracketContext:
    """Resolve the per-bracket lookups the renderer needs, once.

    ``live_state`` is ``BracketService.matchup_live_state``'s output — the
    derived status and watch link per matchup (U2). Optional: a caller that
    doesn't pass it gets exactly the pre-U2 card.
    """
    winner_links = [(m.id, m.winner_to_id, m.winner_to_slot) for m in matches]
    loser_links = [(m.id, m.loser_to_id, m.loser_to_slot) for m in matches]
    rounds_config = (config or {}).get('rounds') or {}
    return BracketContext(
        entry_name=entry_name,
        entry_seed={e.id: e.seed for e in entries},
        match_number=assign_match_numbers(match_nodes(matches)),
        slot_sources=slot_sources(winner_links, loser_links),
        rounds_config=rounds_config,
        scheduled_fmt=format_scheduled,
        on_card_click=on_card_click,
        live_state=live_state or {},
    )


def results_from_matches(matches: List[BracketMatch]) -> List[ResultRow]:
    """Completed matches as opaque-ref result rows for standings computation.

    Shared by the interactive page and the static (cached) view so the two can
    never compute a different table from the same matches.
    """
    rows: List[ResultRow] = []
    for m in matches:
        if m.state != BracketMatchState.COMPLETE:
            continue
        if m.entry1_id is None and m.entry2_id is None:
            continue
        if m.entry2_id is None:
            rows.append(ResultRow(ref1=m.entry1_id, winner=m.entry1_id))
        elif m.entry1_id is None:
            rows.append(ResultRow(ref1=m.entry2_id, winner=m.entry2_id))
        else:
            rows.append(
                ResultRow(ref1=m.entry1_id, ref2=m.entry2_id, winner=m.winner_id)
            )
    return rows


def entry_records(
    entry_ids: List[int], matches: List[BracketMatch]
) -> Dict[int, tuple]:
    """(wins, losses) per entry across completed, non-bye matches of this stage."""
    rec: Dict[int, List[int]] = {eid: [0, 0] for eid in entry_ids}
    for m in matches:
        if m.state != BracketMatchState.COMPLETE or m.winner_id is None:
            continue
        if m.entry1_id is None or m.entry2_id is None:
            continue
        for eid in (m.entry1_id, m.entry2_id):
            if eid in rec:
                rec[eid][0 if eid == m.winner_id else 1] += 1
    return {eid: (w, loss) for eid, (w, loss) in rec.items()}


def render_elimination(
    matches: List[BracketMatch],
    ctx: BracketContext,
    *,
    double: bool,
) -> None:
    """Connector-lined 2-D bracket; DE losers section below winners+finals."""
    if not matches:
        ui.label('No matches yet.').classes('italic-note')
        return

    matches_by_id = {m.id: m for m in matches}
    positive = [m for m in matches if m.round > 0]
    negative = [m for m in matches if m.round < 0]

    if not double:
        layout = layout_section(match_nodes(positive))
        max_wr = max((m.round for m in positive), default=None)
        render_section(None, layout, matches_by_id, ctx, max_winners_round=max_wr)
        return

    grand_final, reset = detect_finals(matches)
    gf_round = grand_final.round if grand_final is not None else None
    reset_round = reset.round if reset is not None else None
    finals_rounds = {r for r in (gf_round, reset_round) if r is not None}
    wb_rounds = [m.round for m in positive if m.round not in finals_rounds]
    max_wr = max(wb_rounds, default=None)
    max_lm = max((abs(m.round) for m in negative), default=None)

    winners_layout = layout_section(match_nodes(positive))
    render_section(
        'Winners bracket', winners_layout, matches_by_id, ctx,
        gf_round=gf_round, reset_round=reset_round,
        max_winners_round=max_wr, max_losers_magnitude=max_lm, double_elim=True,
    )
    if negative:
        losers_layout = layout_section(match_nodes(negative))
        render_section(
            'Losers bracket', losers_layout, matches_by_id, ctx,
            max_losers_magnitude=max_lm, double_elim=True,
        )


def render_elimination_mobile(
    matches: List[BracketMatch],
    ctx: BracketContext,
    *,
    double: bool,
) -> None:
    """Per-round accordion of stacked cards — the phone view (below lt.md)."""
    if not matches:
        return
    positive = sorted({m.round for m in matches if m.round > 0})
    negative = sorted({m.round for m in matches if m.round < 0}, key=abs)

    grand_final, reset = detect_finals(matches) if double else (None, None)
    gf_round = grand_final.round if grand_final is not None else None
    reset_round = reset.round if reset is not None else None
    finals_rounds = {r for r in (gf_round, reset_round) if r is not None}
    max_lm = max((abs(r) for r in negative), default=None) if double else None
    max_wr = max([r for r in positive if r not in finals_rounds], default=None)

    ordered = positive + negative
    by_round: Dict[int, List[BracketMatch]] = {}
    for m in matches:
        by_round.setdefault(m.round, []).append(m)

    def chron(r: int) -> int:
        return r if r >= 0 else 1000 + abs(r)

    open_rounds = [m.round for m in matches if m.state == BracketMatchState.OPEN]
    default_round = (
        min(open_rounds, key=chron) if open_rounds else (ordered[-1] if ordered else None)
    )

    for r in ordered:
        name = round_label(
            r,
            is_grand_final=r == gf_round,
            is_reset=r == reset_round,
            max_winners_round=max_wr,
            max_losers_magnitude=max_lm,
            double_elim=double,
        )
        round_matches = sorted(by_round.get(r, []), key=lambda m: m.position)
        with ui.expansion(name, value=r == default_round) \
                .classes('bracket-round-accordion w-full'):
            _render_round_meta(r, ctx)
            for m in round_matches:
                render_mobile_card(m, ctx)


def _render_round_meta(round_number: int, ctx) -> None:
    """The round's best-of / scheduled time inside its accordion panel.

    The 2-D view carries this in the sticky round header, which the accordion
    replaces — without it the phone view silently drops the two facts a player
    most needs to plan around.
    """
    meta = ctx.rounds_config.get(str(round_number)) or {}
    scheduled, best_of = meta.get('scheduled_at'), meta.get('best_of')
    if not scheduled and not best_of:
        return
    with ui.row().classes('bracket-round-meta'):
        if scheduled:
            # "Round time", not the game's time — see the 2-D header (U3c).
            ui.label(f'Round time: {ctx.scheduled_fmt(scheduled)}') \
                .classes('bracket-header-time')
        if best_of:
            ui.label(f'Best of {best_of}').classes('bracket-badge')
