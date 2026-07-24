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

from datetime import datetime, timezone
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
from application.utils.timezone import format_eastern_display
from models import (
    Bracket,
    BracketEntry,
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
    BracketContext,
    MatchNode,
    assign_match_numbers,
    layout_section,
    register_bracket_view,
    render_section,
    slot_sources,
)
from theme.notify import notify_error
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


def _format_scheduled(iso: str) -> str:
    """A round's stored UTC ISO time → the app's Eastern display string."""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_eastern_display(dt)


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


def _match_nodes(matches: List[BracketMatch]) -> List[MatchNode]:
    return [
        MatchNode(id=m.id, round=m.round, position=m.position, winner_to_id=m.winner_to_id)
        for m in matches
    ]


def _build_context(
    bracket: Bracket,
    entries: List[BracketEntry],
    matches: List[BracketMatch],
    entry_name: Dict[int, str],
    *,
    on_card_click: Optional[object] = None,
) -> BracketContext:
    """Resolve the per-bracket lookups the shared renderer needs, once."""
    winner_links = [(m.id, m.winner_to_id, m.winner_to_slot) for m in matches]
    loser_links = [(m.id, m.loser_to_id, m.loser_to_slot) for m in matches]
    rounds_config = (bracket.config or {}).get('rounds') or {}
    return BracketContext(
        entry_name=entry_name,
        entry_seed={e.id: e.seed for e in entries},
        match_number=assign_match_numbers(_match_nodes(matches)),
        slot_sources=slot_sources(winner_links, loser_links),
        rounds_config=rounds_config,
        scheduled_fmt=_format_scheduled,
        on_card_click=on_card_click,
    )


def _render_elimination(
    matches: List[BracketMatch],
    ctx: BracketContext,
    *,
    double: bool,
) -> None:
    """Connector-lined bracket via the shared renderer; DE losers below winners."""
    if not matches:
        ui.label('No matches yet.').classes('italic-note')
        return

    matches_by_id = {m.id: m for m in matches}
    positive = [m for m in matches if m.round > 0]
    negative = [m for m in matches if m.round < 0]

    if not double:
        layout = layout_section(_match_nodes(positive))
        max_wr = max((m.round for m in positive), default=None)
        render_section(None, layout, matches_by_id, ctx, max_winners_round=max_wr)
        return

    grand_final, reset = _detect_finals(matches)
    gf_round = grand_final.round if grand_final is not None else None
    reset_round = reset.round if reset is not None else None
    finals_rounds = {r for r in (gf_round, reset_round) if r is not None}
    wb_rounds = [m.round for m in positive if m.round not in finals_rounds]
    max_wr = max(wb_rounds, default=None)
    max_lm = max((abs(m.round) for m in negative), default=None)

    # Winners section carries the finals columns at its right edge (the grand
    # final / reset feed from the winners-bracket final); losers below.
    winners_layout = layout_section(_match_nodes(positive))
    render_section(
        'Winners bracket', winners_layout, matches_by_id, ctx,
        gf_round=gf_round, reset_round=reset_round,
        max_winners_round=max_wr, max_losers_magnitude=max_lm,
    )
    losers_layout = layout_section(_match_nodes(negative))
    render_section(
        'Losers bracket', losers_layout, matches_by_id, ctx,
        max_losers_magnitude=max_lm,
    )


def _entry_records(
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


def _build_match_dialog(
    match: BracketMatch,
    entry_name: Dict[int, str],
    entry_seed: Dict[int, Optional[int]],
    records: Dict[int, tuple],
    number: Optional[int],
    *,
    is_staff: bool,
    actor: Optional[User],
    tenant_id: int,
    service: BracketService,
    on_saved: Callable,
) -> None:
    """Match detail dialog: entrants, scores/FF, state, and staff reporting."""
    completed = match.state == BracketMatchState.COMPLETE

    def name_of(entry_id: Optional[int]) -> str:
        return entry_name.get(entry_id, 'TBD') if entry_id is not None else 'TBD'

    with ui.dialog() as dialog, ui.card().classes('w-[26rem] max-w-full'):
        with ui.row().classes('items-center justify-between w-full'):
            ui.label(f'Match {number}' if number else 'Match').classes('text-h6')
            ui.badge(
                match.state.value.title(),
                color=_STATE_COLORS.get(BracketState.ACTIVE, 'grey')
                if match.state == BracketMatchState.OPEN else 'grey',
            )

        for slot, entry_id in ((1, match.entry1_id), (2, match.entry2_id)):
            is_winner = (
                completed and match.winner_id is not None and entry_id == match.winner_id
            )
            score = match.entry1_score if slot == 1 else match.entry2_score
            with ui.row().classes('items-center justify-between w-full q-py-xs'):
                with ui.row().classes('items-center gap-2 no-wrap'):
                    seed = entry_seed.get(entry_id) if entry_id is not None else None
                    if seed is not None:
                        ui.label(f'#{seed}').classes('text-caption text-grey')
                    ui.label(name_of(entry_id)).classes(
                        'text-bold' if is_winner else ''
                    )
                    rec = records.get(entry_id) if entry_id is not None else None
                    if rec is not None and (rec[0] or rec[1]):
                        ui.label(f'({rec[0]}-{rec[1]})').classes('text-caption text-grey')
                if completed and match.forfeit and entry_id is not None and not is_winner:
                    ui.label('FF').classes('text-bold text-negative')
                elif score is not None:
                    ui.label(str(score)).classes('text-bold' if is_winner else '')
                elif is_winner:
                    ui.icon('emoji_events', size='xs').classes('text-primary')

        if match.match_id is not None:
            ui.label('Scheduled to a match room.').classes('text-caption text-grey')

        can_report = (
            is_staff
            and match.state in (BracketMatchState.OPEN, BracketMatchState.COMPLETE)
            and match.entry1_id is not None
            and match.entry2_id is not None
        )
        if can_report:
            ui.separator()
            ui.label(
                'Report result' if match.state == BracketMatchState.OPEN
                else 'Override result'
            ).classes('section-title')
            with ui.row().classes('items-center gap-2 w-full'):
                s1 = ui.number(
                    label=name_of(match.entry1_id), value=match.entry1_score, min=0,
                ).props('dense inputmode=numeric').classes('w-32')
                s2 = ui.number(
                    label=name_of(match.entry2_id), value=match.entry2_score, min=0,
                ).props('dense inputmode=numeric').classes('w-32')
            ff = ui.switch('Forfeit', value=match.forfeit)

            async def save(winner_id: int) -> None:
                e1 = int(s1.value) if s1.value is not None else None
                e2 = int(s2.value) if s2.value is not None else None
                with tenant_scope(tenant_id):
                    try:
                        if match.state == BracketMatchState.OPEN:
                            await service.report_result(
                                actor, match.id, winner_id,
                                entry1_score=e1, entry2_score=e2, forfeit=ff.value,
                            )
                        else:
                            await service.override_result(
                                actor, match.id, winner_id,
                                entry1_score=e1, entry2_score=e2, forfeit=ff.value,
                            )
                    except (ValueError, PermissionError) as ex:
                        notify_error(ex)
                        return
                ui.notify('Result saved', color='positive')
                dialog.close()
                await on_saved()

            with ui.row().classes('gap-2 w-full q-mt-xs'):
                ui.button(
                    f'Winner: {name_of(match.entry1_id)}', icon='emoji_events',
                    on_click=lambda _=None, w=match.entry1_id: save(w),
                ).props('dense color=primary')
                ui.button(
                    f'Winner: {name_of(match.entry2_id)}', icon='emoji_events',
                    on_click=lambda _=None, w=match.entry2_id: save(w),
                ).props('dense color=primary')

        with ui.row().classes('justify-end w-full q-mt-sm'):
            ui.button('Close', on_click=dialog.close).props('flat')
    dialog.open()


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
                records = _entry_records([e.id for e in entries], matches)
                number = assign_match_numbers(_match_nodes(matches)).get(match.id)
                _build_match_dialog(
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
                    toolbar_row = ui.row().classes('bracket-toolbar items-center gap-2 q-mb-sm')
                    wrapper = ui.element('div').classes('bracket-zoomable w-full')
                    with wrapper:
                        ctx = _build_context(
                            bracket, entries, matches, entry_name,
                            on_card_click=on_card_click,
                        )
                        _render_elimination(
                            matches, ctx,
                            double=bracket.format == BracketFormat.DOUBLE_ELIM,
                        )
                    _populate_zoom_toolbar(toolbar_row, wrapper, _live_refresh)
                elif bracket.format == BracketFormat.ROUND_ROBIN:
                    _render_round_robin(entries, matches, entry_name, bracket.config)
                else:
                    _render_swiss(entries, matches, entry_name, bracket.config)

        await render_body()
        register_bracket_view(bracket_id, _live_refresh)
