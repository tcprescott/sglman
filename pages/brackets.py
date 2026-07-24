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

from typing import Callable, Dict, List, Optional

from nicegui import app, background_tasks, context, ui

from middleware.auth import protected_page

from application.services import AuthService, BracketService, get_user_from_discord_id
from application.services.bracket_engines.standings import (
    ResultRow,
    StandingsConfig,
    compute_standings,
)
from application.tenant_context import require_tenant_id, tenant_scope
from models import (
    Bracket,
    BracketEntry,
    BracketEntryStatus,
    BracketFormat,
    BracketMatch,
    BracketMatchState,
    BracketState,
    FeatureFlag,
    Tournament,
    User,
)
from theme.base import BaseLayout
from theme.brackets import (
    assign_match_numbers,
    build_context,
    build_match_dialog,
    entry_records,
    match_nodes,
    register_bracket_view,
    render_elimination,
    render_elimination_mobile,
)
from theme.brackets.tables import render_crosstable, render_pairings, render_standings

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


async def _next_stage_advancement(
    service: BracketService, bracket: Bracket
) -> Optional[dict]:
    """The next stage's advancement rule, if any — drives cut lines / tinting."""
    brackets = await service.list_brackets(bracket.tournament_id)
    nxt = next(
        (b for b in brackets if b.stage_order == bracket.stage_order + 1), None
    )
    if nxt is None or not nxt.config:
        return None
    return (nxt.config or {}).get('advancement')


# Delegated hover-run highlight: hovering any entrant row tints that entrant's
# rows across every match in the bracket (Gracket's data-attribute technique).
_HOVER_RUN_JS = (
    '<script>'
    'if(!window.__wizBracketHover){'
    'window.__wizBracketHover=true;'
    'var t=function(on){return function(e){'
    'var el=e.target.closest?e.target.closest(\'[data-entrant-id]\'):null;'
    'if(!el)return;'
    'var id=el.getAttribute(\'data-entrant-id\');'
    'if(!id)return;'
    'var ns=document.querySelectorAll(\'.bracket-slot[data-entrant-id="\'+id+\'"]\');'
    'for(var i=0;i<ns.length;i++){ns[i].classList.toggle(\'run-highlight\',on);}'
    '};};'
    "document.addEventListener('mouseover',t(true),true);"
    "document.addEventListener('mouseout',t(false),true);"
    '}'
    '</script>'
)


def _install_hover_run() -> None:
    ui.add_body_html(_HOVER_RUN_JS)


def _populate_zoom_toolbar(row, wrapper, refresh: Callable) -> None:
    """Fill the elimination toolbar: zoom −/level/+ (CSS scale) and a refresh."""
    zoom = {'v': 1.0}

    def apply() -> None:
        wrapper.style(f'--bracket-zoom: {zoom["v"]}')
        label.set_text(f'{int(zoom["v"] * 100)}%')

    def step(delta: float) -> None:
        zoom['v'] = max(0.5, min(1.6, round(zoom['v'] + delta, 2)))
        apply()

    with row:
        ui.button(icon='zoom_out', on_click=lambda: step(-0.1)) \
            .props('flat dense round').tooltip('Zoom out')
        label = ui.label('100%').classes('text-caption text-grey')
        ui.button(icon='zoom_in', on_click=lambda: step(0.1)) \
            .props('flat dense round').tooltip('Zoom in')
        ui.space()
        ui.button(icon='refresh', on_click=refresh) \
            .props('flat dense round').tooltip('Refresh')


def _group_letter(group: Optional[int]) -> Optional[str]:
    if group is None:
        return None
    try:
        return chr(ord('A') + (int(group) - 1))
    except (TypeError, ValueError):
        return str(group)


def _render_results_list(
    matches: List[BracketMatch], entry_name: Dict[int, str]
) -> None:
    played = [m for m in matches if m.state == BracketMatchState.COMPLETE]
    upcoming = [m for m in matches if m.state == BracketMatchState.OPEN]
    if not played and not upcoming:
        ui.label('No matches yet.').classes('text-caption text-grey')
        return
    with ui.column().classes('gap-1 w-full'):
        for match in played:
            name1 = _slot_label(match.entry1_id, entry_name, completed=True)
            name2 = _slot_label(match.entry2_id, entry_name, completed=True)
            if match.entry2_id is None or match.entry1_id is None:
                winner = _slot_label(match.winner_id, entry_name, completed=True)
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
    *,
    advancement: Optional[dict] = None,
    complete: bool = False,
) -> None:
    entry_seed = {e.id: e.seed for e in entries}
    tiebreakers = _standings_config(config).tiebreakers
    group_of: Dict[int, Optional[int]] = {}
    for m in matches:
        for eid in (m.entry1_id, m.entry2_id):
            if eid is not None:
                group_of[eid] = m.group_number
    for e in entries:
        group_of.setdefault(e.id, e.group_number)

    groups = sorted({group_of.get(e.id) for e in entries}, key=lambda g: (g is None, g))
    # A per-group advancement rule tints/cuts each group's top `count`.
    per_group_cut = (
        advancement.get('count')
        if advancement and advancement.get('per_group')
        else None
    )

    with ui.element('div').classes('bracket-groups-grid'):
        for group in groups:
            group_entry_ids = [e.id for e in entries if group_of.get(e.id) == group]
            group_matches = [m for m in matches if m.group_number == group]
            with ui.card().classes('bracket-group-card'):
                letter = _group_letter(group)
                ui.label(f'Group {letter}' if letter else 'Standings') \
                    .classes('bracket-section-title')
                if not group_entry_ids:
                    ui.label('No entrants yet.').classes('italic-note')
                    continue
                standings = compute_standings(
                    group_entry_ids,
                    _results_from_matches(group_matches),
                    _standings_config(config),
                )
                render_standings(
                    standings, entry_name, entry_seed, tiebreakers,
                    advancing=per_group_cut, show_elim=complete,
                )
                order_ids = [s.ref for s in standings]
                if 2 <= len(group_entry_ids) <= 10:
                    with ui.expansion('Crosstable').classes('w-full'):
                        render_crosstable(order_ids, group_matches, entry_name)
                with ui.expansion('Matches').classes('w-full'):
                    _render_results_list(group_matches, entry_name)


def _render_swiss(
    entries: List[BracketEntry],
    matches: List[BracketMatch],
    entry_name: Dict[int, str],
    config: Optional[dict],
    *,
    advancement: Optional[dict] = None,
    complete: bool = False,
) -> None:
    entry_seed = {e.id: e.seed for e in entries}
    dropped = {e.id for e in entries if e.status == BracketEntryStatus.DROPPED}
    tiebreakers = _standings_config(config).tiebreakers

    ui.label('Standings').classes('bracket-section-title')
    if not entries:
        ui.label('No entrants yet.').classes('italic-note')
        return
    standings = compute_standings(
        [e.id for e in entries], _results_from_matches(matches), _standings_config(config)
    )
    swiss_cut = advancement.get('count') if advancement else None
    render_standings(
        standings, entry_name, entry_seed, tiebreakers,
        advancing=swiss_cut, show_elim=complete, dropped_ids=dropped,
    )
    if 'head_to_head' in tiebreakers:
        ui.label('Remaining ties are broken by head-to-head result.') \
            .classes('text-caption text-grey')

    rounds = sorted({m.round for m in matches})
    if not rounds:
        return
    records = entry_records([e.id for e in entries], matches)
    open_rounds = [m.round for m in matches if m.state == BracketMatchState.OPEN]
    default_round = max(open_rounds) if open_rounds else max(rounds)

    ui.label('Pairings').classes('bracket-section-title')
    with ui.tabs().classes('w-full') as tabs:
        for r in rounds:
            ui.tab(f'r{r}', label=f'Round {r}')
    with ui.tab_panels(tabs, value=f'r{default_round}').classes('w-full'):
        for r in rounds:
            with ui.tab_panel(f'r{r}'):
                render_pairings(
                    [m for m in matches if m.round == r], entry_name, records,
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
        is_staff = await AuthService.is_staff(user)
        await BaseLayout(
            user=user, show_admin=show_admin, show_volunteer=user is not None,
        ).render()
        ui.add_head_html('<link rel="stylesheet" href="/static/css/brackets.css">')
        _install_hover_run()

        # Captured while the request context is live; row-action/live-refresh
        # handlers fire from detached client events that have lost the tenant
        # contextvar, so scoped reads/writes rebind it.
        tenant_id = require_tenant_id()
        service = BracketService()

        async def _live_refresh() -> None:
            render_body.refresh()

        async def open_match_dialog(match_id: int, client) -> None:
            with client:
                with tenant_scope(tenant_id):
                    bracket = await service.get_bracket(bracket_id)
                    if bracket is None:
                        return
                    entrants = await service.list_entrants(bracket.tournament_id)
                    entries = await service.list_entries(bracket_id)
                    matches = await service.list_matches(bracket_id)
                name_by_entrant = {en.id: en.display_name for en in entrants}
                entry_name = {
                    e.id: name_by_entrant.get(e.entrant_id, 'Unknown') for e in entries
                }
                entry_seed = {e.id: e.seed for e in entries}
                match = next((m for m in matches if m.id == match_id), None)
                if match is None:
                    return
                records = entry_records([e.id for e in entries], matches)
                number = assign_match_numbers(match_nodes(matches)).get(match.id)
                build_match_dialog(
                    match, entry_name, entry_seed, records, number,
                    is_staff=is_staff, actor=user, tenant_id=tenant_id,
                    service=service, on_saved=_live_refresh,
                )

        def on_card_click(match_id: int) -> None:
            background_tasks.create(open_match_dialog(match_id, context.client))

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

                if bracket.format in (BracketFormat.SINGLE_ELIM, BracketFormat.DOUBLE_ELIM):
                    double = bracket.format == BracketFormat.DOUBLE_ELIM
                    ctx = build_context(
                        bracket.config, entries, matches, entry_name,
                        on_card_click=on_card_click,
                    )
                    # 2-D connector bracket (>= md); a per-round accordion (< md).
                    with ui.element('div').classes('bracket-2d w-full'):
                        toolbar_row = ui.row().classes('bracket-toolbar items-center gap-2 q-mb-sm')
                        wrapper = ui.element('div').classes('bracket-zoomable w-full')
                        with wrapper:
                            render_elimination(matches, ctx, double=double)
                        _populate_zoom_toolbar(toolbar_row, wrapper, _live_refresh)
                    with ui.element('div').classes('bracket-mobile-list w-full'):
                        render_elimination_mobile(matches, ctx, double=double)
                else:
                    advancement = await _next_stage_advancement(service, bracket)
                    complete = bracket.state == BracketState.COMPLETE
                    if bracket.format == BracketFormat.ROUND_ROBIN:
                        _render_round_robin(
                            entries, matches, entry_name, bracket.config,
                            advancement=advancement, complete=complete,
                        )
                    else:
                        _render_swiss(
                            entries, matches, entry_name, bracket.config,
                            advancement=advancement, complete=complete,
                        )

        await render_body()
        register_bracket_view(bracket_id, _live_refresh)
