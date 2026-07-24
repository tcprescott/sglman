"""Public bracket view pages (native brackets, unit B11).

Read-only presentation for a tournament's bracket stages: a per-tournament index
listing every stage and a per-bracket detail that renders each stage by its
format —

* single / double elimination: a column-per-round card view (winners bracket,
  plus a separate losers-bracket section for double elim), each match a card
  showing both entrant display names with the winner highlighted;
* round robin: per-group standings tables plus a results list;
* swiss: a standings table plus per-round results.

Presentation only: reads through :class:`BracketService`, does read-only
load-or-404 ORM lookups for the owning tournament, and computes live display
standings with the pure :func:`compute_standings` helper. No ORM writes.
"""

from typing import Dict, List, Optional

from nicegui import app, ui

from middleware.auth import protected_page

from application.services import AuthService, BracketService, get_user_from_discord_id
from application.services.bracket_engines.standings import (
    ResultRow,
    StandingsConfig,
    compute_standings,
)
from application.tenant_context import require_tenant_id
from models import (
    BracketEntry,
    BracketFormat,
    BracketMatch,
    BracketMatchState,
    BracketState,
    FeatureFlag,
    Tournament,
)
from theme.base import BaseLayout
from theme.tables.mobile_grid import enable_mobile_grid

_FORMAT_LABELS = {
    BracketFormat.SINGLE_ELIM: 'Single elimination',
    BracketFormat.DOUBLE_ELIM: 'Double elimination',
    BracketFormat.SWISS: 'Swiss',
    BracketFormat.ROUND_ROBIN: 'Round robin',
}

_STATE_COLORS = {
    BracketState.DRAFT: 'grey',
    BracketState.ACTIVE: 'positive',
    BracketState.COMPLETE: 'primary',
}


def _format_label(fmt: BracketFormat) -> str:
    return _FORMAT_LABELS.get(fmt, fmt.value)


def _standings_config(config: Optional[dict]) -> StandingsConfig:
    """Build a :class:`StandingsConfig` from a bracket's stored config, if any."""
    config = config or {}
    kwargs: Dict[str, object] = {}
    for key in ('win_points', 'draw_points', 'loss_points', 'bye_points', 'omw_floor'):
        value = config.get(key)
        if value is not None:
            kwargs[key] = value
    tiebreakers = config.get('tiebreakers')
    if tiebreakers:
        kwargs['tiebreakers'] = tuple(tiebreakers)
    return StandingsConfig(**kwargs)


def _results_from_matches(matches: List[BracketMatch]) -> List[ResultRow]:
    """Completed matches as opaque-ref result rows for standings computation."""
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


def _slot_label(
    entry_id: Optional[int], entry_name: Dict[int, str], *, completed: bool
) -> str:
    if entry_id is not None:
        return entry_name.get(entry_id, 'Unknown')
    return 'BYE' if completed else 'TBD'


def _round_label(round_: int, rounds: List[int]) -> str:
    if round_ < 0:
        return f'Losers Round {abs(round_)}'
    if round_ == max(r for r in rounds if r > 0):
        return 'Final'
    return f'Round {round_}'


def _match_card(match: BracketMatch, entry_name: Dict[int, str]) -> None:
    """Render one bracket match as a compact two-slot card."""
    completed = match.state == BracketMatchState.COMPLETE
    with ui.card().classes('q-pa-sm q-mb-sm').style('min-width: 180px'):
        for entry_id in (match.entry1_id, match.entry2_id):
            is_winner = completed and match.winner_id is not None and entry_id == match.winner_id
            classes = 'text-weight-bold text-positive' if is_winner else ''
            with ui.row().classes('items-center justify-between no-wrap w-full gap-2'):
                ui.label(_slot_label(entry_id, entry_name, completed=completed)).classes(classes)
                if is_winner:
                    ui.icon('emoji_events', size='xs').classes('text-positive')


def _detect_finals(
    matches: List[BracketMatch],
) -> tuple[Optional[BracketMatch], Optional[BracketMatch]]:
    """Structurally locate a double-elim grand final and its optional reset.

    There is no ``label``/``is_reset`` column, so detect by graph shape:

    * **Grand Final** — the positive-round match with an incoming feeder from a
      **negative** (losers-bracket) round. There is exactly one.
    * **Reset** — the positive-round match the Grand Final itself feeds into
      (via its ``winner_to``/``loser_to`` pointers). Absent when
      ``grand_final_reset`` is disabled.

    Either may be ``None`` for an empty or not-yet-generated finals stage.
    """
    by_id = {m.id: m for m in matches}
    # For each target match, the rounds of the matches feeding into it.
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

    reset: Optional[BracketMatch] = None
    if grand_final is not None:
        for target_id in (grand_final.winner_to_id, grand_final.loser_to_id):
            candidate = by_id.get(target_id) if target_id is not None else None
            if candidate is not None and candidate.round > 0:
                reset = candidate
                break
    return grand_final, reset


def _render_round_columns(
    title: str,
    section_rounds: List[int],
    matches: List[BracketMatch],
    all_rounds: List[int],
    entry_name: Dict[int, str],
) -> None:
    if not section_rounds:
        return
    ui.label(title).classes('section-title q-mt-md')
    # Wide bracket: keep the page body from overflowing on mobile.
    with ui.element('div').style('overflow-x: auto; width: 100%'):
        with ui.row().classes('no-wrap items-start gap-4'):
            for round_ in section_rounds:
                round_matches = sorted(
                    (m for m in matches if m.round == round_),
                    key=lambda m: m.position,
                )
                with ui.column().classes('gap-1'):
                    ui.label(_round_label(round_, all_rounds)).classes('text-caption text-bold')
                    for match in round_matches:
                        _match_card(match, entry_name)


def _render_finals_columns(
    grand_final: Optional[BracketMatch],
    reset: Optional[BracketMatch],
    entry_name: Dict[int, str],
) -> None:
    if grand_final is None:
        return
    ui.label('Finals').classes('section-title q-mt-md')
    with ui.element('div').style('overflow-x: auto; width: 100%'):
        with ui.row().classes('no-wrap items-start gap-4'):
            for match, label in (
                (grand_final, 'Grand Final'),
                (reset, 'Grand Final (reset)'),
            ):
                if match is None:
                    continue
                with ui.column().classes('gap-1'):
                    ui.label(label).classes('text-caption text-bold')
                    _match_card(match, entry_name)


def _render_elimination(
    matches: List[BracketMatch],
    entry_name: Dict[int, str],
    *,
    double: bool,
) -> None:
    """Column-per-round card layout; losers bracket in its own section for DE."""
    if not matches:
        ui.label('No matches yet.').classes('italic-note')
        return

    all_rounds = sorted({m.round for m in matches})

    if not double:
        winners_rounds = [r for r in all_rounds if r > 0]
        _render_round_columns('Bracket', winners_rounds, matches, all_rounds, entry_name)
        return

    grand_final, reset = _detect_finals(matches)
    finals_rounds = {m.round for m in (grand_final, reset) if m is not None}
    winners_rounds = [r for r in all_rounds if r > 0 and r not in finals_rounds]
    # Losers rounds read chronologically left-to-right: -1 first, then the
    # progressively more-negative rounds (losers final is most-negative).
    losers_rounds = sorted((r for r in all_rounds if r < 0), key=abs)

    _render_round_columns('Winners bracket', winners_rounds, matches, all_rounds, entry_name)
    _render_round_columns('Losers bracket', losers_rounds, matches, all_rounds, entry_name)
    _render_finals_columns(grand_final, reset, entry_name)


def _render_standings_table(
    entry_ids: List[int],
    matches: List[BracketMatch],
    entry_name: Dict[int, str],
    config: Optional[dict],
    *,
    key_prefix: str,
) -> None:
    if not entry_ids:
        ui.label('No entrants yet.').classes('italic-note')
        return
    standings = compute_standings(
        entry_ids, _results_from_matches(matches), _standings_config(config)
    )
    columns = [
        {'name': 'rank', 'label': '#', 'field': 'rank', 'sortable': True},
        {'name': 'name', 'label': 'Entrant', 'field': 'name', 'sortable': True},
        {'name': 'record', 'label': 'W-L-D', 'field': 'record'},
        {'name': 'points', 'label': 'Points', 'field': 'points', 'sortable': True},
    ]
    rows = [
        {
            # BracketEntry id — a unique row key; display_name can duplicate
            # (e.g. two "TBD" placeholders), which collides Quasar's row_key.
            'entry_id': s.ref,
            'rank': s.rank,
            'name': entry_name.get(s.ref, 'Unknown'),
            'record': f'{s.wins}-{s.losses}-{s.draws}'
            + (f' ({s.byes} bye)' if s.byes else ''),
            'points': f'{s.points:g}',
        }
        for s in standings
    ]
    table = ui.table(
        columns=columns, rows=rows, row_key='entry_id', pagination=0
    ).classes('full-width')
    enable_mobile_grid(table, columns)


def _render_results_list(
    matches: List[BracketMatch], entry_name: Dict[int, str]
) -> None:
    played = [m for m in matches if m.state == BracketMatchState.COMPLETE]
    upcoming = [m for m in matches if m.state == BracketMatchState.OPEN]
    if not played and not upcoming:
        return
    with ui.column().classes('gap-1 w-full'):
        for match in played:
            completed = True
            name1 = _slot_label(match.entry1_id, entry_name, completed=completed)
            name2 = _slot_label(match.entry2_id, entry_name, completed=completed)
            if match.entry2_id is None or match.entry1_id is None:
                winner = _slot_label(match.winner_id, entry_name, completed=completed)
                ui.label(f'{winner} — bye').classes('text-caption')
            else:
                winner_name = entry_name.get(match.winner_id, 'Unknown')
                loser_name = name2 if match.winner_id == match.entry1_id else name1
                ui.label(f'{winner_name} def. {loser_name}').classes('text-caption')
        for match in upcoming:
            name1 = _slot_label(match.entry1_id, entry_name, completed=False)
            name2 = _slot_label(match.entry2_id, entry_name, completed=False)
            ui.label(f'{name1} vs {name2}').classes('text-caption text-grey-6')


def _render_round_robin(
    entries: List[BracketEntry],
    matches: List[BracketMatch],
    entry_name: Dict[int, str],
    config: Optional[dict],
) -> None:
    group_of: Dict[int, Optional[int]] = {}
    for m in matches:
        for eid in (m.entry1_id, m.entry2_id):
            if eid is not None:
                group_of[eid] = m.group_number
    for e in entries:
        group_of.setdefault(e.id, e.group_number)

    groups = sorted({group_of.get(e.id) for e in entries}, key=lambda g: (g is None, g))
    for group in groups:
        group_entry_ids = [e.id for e in entries if group_of.get(e.id) == group]
        group_matches = [m for m in matches if m.group_number == group]
        title = f'Group {group}' if group is not None else 'Standings'
        ui.label(title).classes('section-title q-mt-md')
        _render_standings_table(
            group_entry_ids, group_matches, entry_name, config,
            key_prefix=f'rr-{group}',
        )
        _render_results_list(group_matches, entry_name)


def _render_swiss(
    entries: List[BracketEntry],
    matches: List[BracketMatch],
    entry_name: Dict[int, str],
    config: Optional[dict],
) -> None:
    ui.label('Standings').classes('section-title q-mt-md')
    _render_standings_table(
        [e.id for e in entries], matches, entry_name, config, key_prefix='swiss',
    )
    rounds = sorted({m.round for m in matches})
    for round_ in rounds:
        ui.label(f'Round {round_}').classes('text-caption text-bold q-mt-sm')
        _render_results_list(
            [m for m in matches if m.round == round_], entry_name
        )


def create() -> None:
    @protected_page('/tournament/{tournament_id}/brackets', feature=FeatureFlag.BRACKETS)
    async def bracket_index(tournament_id: int) -> None:
        ui.page_title('Wizzrobe — Brackets')
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        show_admin = await AuthService.can_view_admin(user)
        await BaseLayout(
            user=user, show_admin=show_admin, show_volunteer=user is not None,
        ).render()

        service = BracketService()
        tournament = await Tournament.get_or_none(
            id=tournament_id, tenant_id=require_tenant_id()
        )
        if tournament is None:
            ui.label('Tournament not found.').classes('text-error')
            return

        brackets = await service.list_brackets(tournament_id)

        with ui.card().classes('page-container-narrow w-full q-pa-lg q-mt-md column'):
            ui.label(f'{tournament.name} — Brackets').classes('page-title')
            ui.separator().classes('separator-spacing')
            if not brackets:
                ui.label('No brackets have been created for this tournament.').classes('italic-note')
                return
            for bracket in brackets:
                with ui.card().classes('w-full q-pa-md q-mb-sm'):
                    with ui.row().classes('items-center justify-between w-full'):
                        with ui.column().classes('gap-0'):
                            ui.label(bracket.name).classes('text-subtitle1 text-bold')
                            ui.label(
                                f'Stage {bracket.stage_order + 1} · {_format_label(bracket.format)}'
                            ).classes('text-caption')
                        with ui.row().classes('items-center gap-2'):
                            ui.badge(
                                bracket.state.value.title(),
                                color=_STATE_COLORS.get(bracket.state, 'grey'),
                            )
                            ui.button(
                                'View', icon='visibility',
                                on_click=lambda bid=bracket.id: ui.navigate.to(
                                    f'/brackets/{bid}'
                                ),
                            ).props('flat dense')

    @protected_page('/brackets/{bracket_id}', feature=FeatureFlag.BRACKETS)
    async def bracket_detail(bracket_id: int) -> None:
        ui.page_title('Wizzrobe — Bracket')
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        show_admin = await AuthService.can_view_admin(user)
        await BaseLayout(
            user=user, show_admin=show_admin, show_volunteer=user is not None,
        ).render()

        service = BracketService()

        @ui.refreshable
        async def render_body() -> None:
            bracket = await service.get_bracket(bracket_id)
            if bracket is None:
                ui.label('Bracket not found.').classes('text-error')
                return

            entrants = await service.list_entrants(bracket.tournament_id)
            entrant_name = {en.id: en.display_name for en in entrants}
            entries = await service.list_entries(bracket_id)
            entry_name = {
                e.id: entrant_name.get(e.entrant_id, 'Unknown') for e in entries
            }
            matches = await service.list_matches(bracket_id)

            with ui.card().classes('page-container w-full q-pa-lg q-mt-md column'):
                with ui.row().classes('items-center justify-between w-full'):
                    with ui.column().classes('gap-0'):
                        ui.label(bracket.name).classes('page-title')
                        ui.label(
                            f'Stage {bracket.stage_order + 1} · {_format_label(bracket.format)}'
                        ).classes('text-caption')
                    ui.badge(
                        bracket.state.value.title(),
                        color=_STATE_COLORS.get(bracket.state, 'grey'),
                    )
                ui.button(
                    'All stages', icon='list',
                    on_click=lambda: ui.navigate.to(
                        f'/tournament/{bracket.tournament_id}/brackets'
                    ),
                ).props('flat dense')
                ui.separator().classes('separator-spacing')

                if bracket.state == BracketState.DRAFT or not matches:
                    ui.label('This stage has not started yet.').classes('italic-note')
                    if entries:
                        ui.label('Seeded entrants').classes('section-title q-mt-md')
                        with ui.column().classes('gap-1 w-full'):
                            for entry in entries:
                                seed = f'#{entry.seed} · ' if entry.seed is not None else ''
                                ui.label(
                                    f'{seed}{entry_name.get(entry.id, "Unknown")}'
                                ).classes('text-caption')
                    return

                if bracket.format == BracketFormat.SINGLE_ELIM:
                    _render_elimination(matches, entry_name, double=False)
                elif bracket.format == BracketFormat.DOUBLE_ELIM:
                    _render_elimination(matches, entry_name, double=True)
                elif bracket.format == BracketFormat.ROUND_ROBIN:
                    _render_round_robin(entries, matches, entry_name, bracket.config)
                else:
                    _render_swiss(entries, matches, entry_name, bracket.config)

        await render_body()
