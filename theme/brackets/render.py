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

from application.utils.timezone import format_eastern_display
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
    return format_eastern_display(dt)


def match_nodes(matches: List[BracketMatch]) -> List[MatchNode]:
    return [
        MatchNode(id=m.id, round=m.round, position=m.position, winner_to_id=m.winner_to_id)
        for m in matches
    ]


def detect_finals(
    matches: List[BracketMatch],
) -> Tuple[Optional[BracketMatch], Optional[BracketMatch]]:
    """Structurally locate a double-elim grand final and its optional reset.

    * **Grand Final** — the positive-round match with an incoming feeder from a
      **negative** (losers-bracket) round.
    * **Reset** — the positive-round match the grand final itself feeds into.
    Either may be ``None`` for an empty or not-yet-generated finals stage.
    """
    by_id = {m.id: m for m in matches}
    incoming_rounds: Dict[int, List[int]] = {}
    for m in matches:
        for target_id in (m.winner_to_id, m.loser_to_id):
            if target_id is not None:
                incoming_rounds.setdefault(target_id, []).append(m.round)

    grand_final: Optional[BracketMatch] = None
    for m in matches:
        if m.round > 0 and any(r < 0 for r in incoming_rounds.get(m.id, ())):
            grand_final = m
            break

    if grand_final is None:
        # A 2-entrant double elim has no losers bracket (the WB final's loser
        # drops straight into the grand final via loser_to), so the negative-feeder
        # scan finds nothing. Fall back to the lowest-round positive match that is
        # a loser_to target. (Single elim has no loser_to links, so this stays a
        # no-op there.)
        loser_targets = {m.loser_to_id for m in matches if m.loser_to_id is not None}
        candidates = [m for m in matches if m.round > 0 and m.id in loser_targets]
        if candidates:
            grand_final = min(candidates, key=lambda m: m.round)

    reset: Optional[BracketMatch] = None
    if grand_final is not None:
        for target_id in (grand_final.winner_to_id, grand_final.loser_to_id):
            candidate = by_id.get(target_id) if target_id is not None else None
            if candidate is not None and candidate.round > 0:
                reset = candidate
                break
    return grand_final, reset


def build_context(
    config: Optional[dict],
    entries,
    matches: List[BracketMatch],
    entry_name: Dict[int, str],
    *,
    on_card_click: Optional[Callable[[int], None]] = None,
) -> BracketContext:
    """Resolve the per-bracket lookups the renderer needs, once."""
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
    )


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
            for m in round_matches:
                render_mobile_card(m, ctx)
