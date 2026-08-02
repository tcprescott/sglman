"""Admin Schedule Management Page"""


from typing import Any

from nicegui import ui

from application.tenant_context import require_tenant_id
from application.utils.crew_queue import pending_crew_summary
from models import Match
from pages.admin_tabs.links import SCHEDULE, admin_url
from theme.dialog.match_dialog import AdminMatchDialog
from theme.tables.match import MatchTableView
from theme.tables.match_access import MatchBoardAccess
from theme.tables.match_lifecycle import MatchLifecycleHandlers
from theme.tables.preferences import TableKeys


def admin_schedule_page(
    access: MatchBoardAccess | None = None,
    match_id: int | None = None,
    tournament_ids: list[int] | None = None,
) -> None:
    """The admin Schedule board.

    ``access`` is what this viewer may do (see ``match_access``); a board built
    without one offers nothing but the read.

    ``tournament_ids`` narrows the board to the tournaments the viewer operates.
    It is set for a tournament admin or crew coordinator — whose authority *is*
    per-tournament — and left ``None`` for staff and the stream manager, whose
    authority is community-wide.
    """
    access = access or MatchBoardAccess()
    with ui.column().classes('page-container-wide') as page_container:
        # Header section
        with ui.row().classes('header-row'):
            ui.label('Schedule Management').classes('page-title')

        ui.separator().classes('separator-spacing')

        # Same reasoning as the match_id chip below: a board showing a subset
        # with no explanation reads as a board that lost rows.
        if tournament_ids is not None:
            with ui.row().classes('items-center gap-2 q-mb-sm'):
                with ui.element('span').classes('wiz-chip wiz-chip--neutral'):
                    ui.icon('emoji_events', size='14px')
                    n = len(tournament_ids)
                    ui.label(f'Showing the {n} tournament{"" if n == 1 else "s"} you run')

        # A report linked here naming one match. Say so and offer the way out —
        # a one-row board with no explanation reads as a broken board.
        if match_id:
            with ui.row().classes('items-center gap-2 q-mb-sm'):
                with ui.element('span').classes('wiz-chip wiz-chip--pending'):
                    ui.icon('filter_alt', size='14px')
                    ui.label(f'Showing match #{match_id} only')
                ui.button(
                    'Show all matches', icon='clear',
                    on_click=lambda: ui.navigate.to(admin_url(SCHEDULE)),
                ).props('flat dense color=primary')

        columns = [
            # A pencil, not the primary key. The id was this board's only edit
            # affordance and the last database value on a community-facing
            # screen; the proctor board keeps its '#' because a proctor really
            # does call a match out by number.
            {'name': 'edit', 'label': '', 'field': 'id'},
            {'name': 'tournament', 'label': 'Tournament',
                'field': 'tournament', 'sortable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At',
                'field': 'scheduled_at', 'sortable': True},
            {'name': 'state', 'label': 'State', 'field': 'state', 'sortable': True},
            # Not sortable: a joined roster of names, where the sort would run on
            # whoever happens to be listed first.
            {'name': 'players', 'label': 'Players', 'field': 'players'},
            {'name': 'commentators', 'label': 'Commentators', 'field': 'commentators'},
            {'name': 'trackers', 'label': 'Trackers', 'field': 'trackers'},
            {'name': 'stage', 'label': 'Stage',
                'field': 'stage', 'sortable': True},
            # Sorts present-vs-absent, which is the question actually asked of it.
            {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed', 'sortable': True},
        ]

        def get_query():
            # The handlers' per-row lookup. The *board's* rows come from
            # MatchDisplayService, so the scope has to be passed to the view as
            # well (``scope_tournament_ids``) — narrowing only here would leave
            # the chip above claiming a scope the board never applied.
            qs = Match.filter(tenant_id=require_tenant_id())
            if tournament_ids is not None:
                qs = qs.filter(tournament_id__in=tournament_ids)
            return qs

        # Creating a match is a scheduling action, not a lifecycle one, so it
        # stays here rather than moving into MatchLifecycleHandlers.
        async def submit_admin_match():
            async def after_submit():
                await table_view.refresh()
            with page_container:
                dialog = AdminMatchDialog(on_submit=after_submit)
                await dialog.open()

        extra_slots: dict = {}

        # Bound after the view exists (two-phase; see MatchLifecycleHandlers).
        table_view: Any = None

        # Built before the view so the view can be handed a callback that
        # refreshes it; guarded because the view's first load can land before
        # the local name is bound.
        @ui.refreshable
        def review_queue() -> None:
            # The strip counts confirmation work. A viewer who cannot confirm —
            # a crew coordinator — would be reading a queue they cannot act on.
            if not access.confirm:
                return
            rows: list = table_view.table.rows if table_view else []
            pending = [r for r in rows if r.get('state') == 'Finished']
            if not pending:
                return
            # A proctor flagged these as contested. Counted separately and shown
            # first: a disputed result needs a decision, an unflagged one only
            # needs a click.
            flagged = [r for r in pending if r.get('needs_review')]
            # Finished with nobody recorded is a third thing again: it cannot be
            # confirmed at all (``confirm_match`` refuses it), so counting it as
            # "awaiting confirmation" overstates the one-click pile the admin is
            # planning their queue from.
            resultless = [r for r in pending if not r.get('has_result')]
            confirmable = [r for r in pending if r.get('has_result')]
            with ui.row().classes('items-center gap-2 q-mb-sm'):
                # ui.element + ui.label rather than ui.html: NiceGUI's raw-HTML
                # sinks are reserved for static literals (check_markdown_xss).
                if flagged:
                    with ui.element('span').classes('wiz-chip wiz-chip--cancelled'):
                        ui.icon('report_problem', size='14px')
                        ui.label(f'Flagged for review: {len(flagged)}')
                if resultless:
                    with ui.element('span').classes('wiz-chip wiz-chip--cancelled'):
                        ui.icon('report_problem', size='14px')
                        ui.label(f'No result recorded: {len(resultless)}')
                with ui.element('span').classes('wiz-chip wiz-chip--pending'):
                    ui.icon('flag', size='14px')
                    ui.label(f'Awaiting confirmation: {len(confirmable)}')
                ui.button(
                    'Show only these', icon='filter_alt', on_click=lambda: _only_finished(),
                ).props('flat dense color=primary')

        # The crew half of the same idea. A pending signup was communicated to
        # staff by text colour and nothing else: the words "pending", "awaiting
        # approval" and "to approve" appeared nowhere on this page, and
        # `.st-pending` is the same class the overdue-timestamp cell uses, so
        # most elements carrying it on a given board were not crew at all.
        @ui.refreshable
        def crew_queue() -> None:
            if not access.approve_crew:
                return
            rows: list = table_view.table.rows if table_view else []
            pending = pending_crew_summary(rows)
            if not pending.total:
                return
            with ui.row().classes('items-center gap-2 q-mb-sm'):
                with ui.element('span').classes('wiz-chip wiz-chip--pending'):
                    ui.icon('assignment_ind', size='14px')
                    ui.label(pending.label)
                ui.button(
                    'Show only these', icon='filter_alt',
                    on_click=lambda: table_view._bg(
                        table_view.focus_matches(pending.match_ids)),
                ).props('flat dense color=primary')
                if table_view is not None and table_view.match_ids:
                    ui.button(
                        'Show all matches', icon='clear',
                        on_click=lambda: table_view._bg(table_view.focus_matches(None)),
                    ).props('flat dense color=primary')

        crew_queue()

        def _only_finished() -> None:
            # Assigning the select's value fires _on_state_filter_change, which
            # stores the choice and reloads the table.
            table_view.state_filter.value = ['Finished']

        review_queue()

        handlers = MatchLifecycleHandlers(page_container, access=access)
        table_view = MatchTableView(
            columns=columns,
            get_query=get_query,
            admin_controls=True,
            access=access,
            submit_match_callback=submit_admin_match if access.edit else None,
            extra_slots=extra_slots,
            storage_key='admin_schedule',
            table_key=TableKeys.ADMIN_SCHEDULE,
            searchable=True,
            # The admin's job *is* the Finished-not-yet-Confirmed set, so it
            # must be on screen without them discovering the State filter.
            default_state_filter=['Scheduled', 'Checked In', 'Started', 'Finished'],
            match_ids=[match_id] if match_id else None,
            scope_tournament_ids=tournament_ids,
            on_rows_changed=lambda _rows: (review_queue.refresh(), crew_queue.refresh()),
            **handlers.callbacks(),
        )
        handlers.table_view = table_view

        # Route through the view's _bg so the tab-switch refresh rebinds the
        # tenant (the selected_tab handler runs in a detached task that lost it).
        def on_tab_selected():
            table_view._bg(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Schedule' else None)
