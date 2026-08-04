"""Admin Schedule Management Page"""


from typing import Any

from nicegui import background_tasks, context, ui

from application.services import MatchRescheduleService
from application.tenant_context import require_tenant_id
from application.utils.timezone import format_local_display
from models import Match, RescheduleRequestKind, RescheduleRequestStatus
from pages.admin_tabs.links import SCHEDULE, admin_url
from theme.dialog.match_dialog import AdminMatchDialog
from theme.dialog.reschedule_decision_dialog import RescheduleDecisionDialog
from theme.realtime import register_view
from theme.tables.admin_crud import current_actor
from theme.tables.match import MatchTableView
from theme.tables.match_access import MatchBoardAccess
from theme.tables.match_lifecycle import MatchLifecycleHandlers
from theme.tables.preferences import TableKeys

# How many requests the strip names individually before collapsing to a count.
# Enough to answer a couple without leaving the board, few enough that a busy
# day does not push the schedule off screen.
_STRIP_REQUEST_LIMIT = 3


def _request_chip_label(request) -> str:
    """Who asked, and for what — short enough to sit on a chip."""
    who = request.requested_by.preferred_name
    if request.kind is RescheduleRequestKind.CANCEL:
        return f'{who}: cancel'
    if request.proposed_at:
        return f'{who}: {format_local_display(request.proposed_at)}'
    return f'{who}: any time'


async def _render_reschedule_queue(
    section, anchor, request_id, open_decision, client, *, may_decide: bool,
) -> None:
    """Draw the strip into its anchor, then open a deep-linked request's dialog.

    Sequenced rather than concurrent: the dialog's Approve refreshes the strip,
    so the strip has to exist first. Runs as a background task, hence the
    explicit client — the strip's own ``ui.*`` calls need a slot too — and it
    renders inside ``anchor`` so the strip keeps its place above the board
    rather than landing wherever the task ran.

    ``may_decide`` gates the deep link as well as the strip. A stream manager or
    crew coordinator reaches this board with ``edit=False``; a forwarded
    ``?reschedule_request=`` would otherwise show them the requester's reason
    and two buttons the service then refuses.
    """
    with client, anchor:
        await section()
    if request_id is not None and may_decide:
        await open_decision(int(request_id), client)


def admin_schedule_page(
    access: MatchBoardAccess | None = None,
    match_id: int | None = None,
    tournament_ids: list[int] | None = None,
    reschedule_request: int | None = None,
) -> None:
    """The admin Schedule board.

    ``access`` is what this viewer may do (see ``match_access``); a board built
    without one offers nothing but the read.

    ``tournament_ids`` narrows the board to the tournaments the viewer operates.
    It is set for a tournament admin or crew coordinator — whose authority *is*
    per-tournament — and left ``None`` for staff and the stream manager, whose
    authority is community-wide.

    ``reschedule_request`` is a request id arriving from the staff DM's button;
    its decision dialog opens once the board has rendered.
    """
    access = access or MatchBoardAccess()
    with ui.column().classes('page-container-wide') as page_container:
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

        # An empty anchor claiming this strip's place in the layout, filled by a
        # background task once the table exists. Without it the strip renders
        # wherever the task happens to run — which is the end of the page, below
        # the board, where staff would have to scroll past every match to find
        # the thing waiting on them.
        reschedule_anchor = ui.column().classes('full-width gap-0')

        # The third queue on this board: players asking staff to move or call
        # off a match. Counted separately from the two above because it is the
        # only one where somebody is waiting on a reply.
        @ui.refreshable
        async def reschedule_queue() -> None:
            if not access.edit:
                return
            actor = await current_actor()
            if actor is None:
                return
            # Narrowed like the board below it: a tournament admin shown a
            # request on somebody else's tournament gets a dialog whose Approve
            # is refused by ``can_crud_match``.
            pending = await MatchRescheduleService().list_pending(
                actor, tournament_ids=tournament_ids,
            )
            if not pending:
                return
            with ui.row().classes('items-center gap-2 q-mb-sm'):
                with ui.element('span').classes('wiz-chip wiz-chip--pending'):
                    ui.icon('edit_calendar', size='14px')
                    ui.label(
                        f'{len(pending)} reschedule request'
                        f'{"s" if len(pending) != 1 else ""} waiting'
                    )
                for request in pending[:_STRIP_REQUEST_LIMIT]:
                    ui.button(
                        _request_chip_label(request),
                        icon='open_in_new',
                        on_click=lambda _=None, r=request: background_tasks.create(
                            _open_decision(r.id, context.client)
                        ),
                    ).props('flat dense color=primary')
                if len(pending) > _STRIP_REQUEST_LIMIT:
                    ui.label(
                        f'+{len(pending) - _STRIP_REQUEST_LIMIT} more'
                    ).classes('text-caption text-grey-7')

        async def _open_decision(request_id: int, client) -> None:
            """Open one request's decision dialog, from the strip or a DM link.

            Takes the client because both entry points run it as a background
            task, where the slot stack is empty and every ``ui.*`` call below —
            the notice and the dialog itself — would otherwise have nowhere to
            render.
            """
            with client:
                service = MatchRescheduleService()
                request = await service.get_by_id(request_id)
                if request is None or request.status is not RescheduleRequestStatus.PENDING:
                    # A DM outlives the request it points at — someone else may
                    # have answered it. Saying so beats a button that does nothing.
                    ui.notify('That request has already been dealt with.', color='warning')
                    return
                actor = await current_actor()
                if actor is None:
                    # A session that outlived its account, or one deactivated
                    # since the page loaded. Caught here rather than let through
                    # to fail as a PermissionError from inside the decision.
                    ui.notify('Log in again to decide this.', color='warning')
                    return

                async def after():
                    reschedule_queue.refresh()
                    await table_view.refresh()

                await RescheduleDecisionDialog(request, actor, on_decision=after).open()

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
            on_rows_changed=lambda _rows: review_queue.refresh(),
            **handlers.callbacks(),
        )
        handlers.table_view = table_view

        # After the table exists, so the strip's buttons can refresh it, and so
        # the deep-linked dialog opens over a rendered board.
        background_tasks.create(_render_reschedule_queue(
            reschedule_queue, reschedule_anchor, reschedule_request,
            _open_decision, context.client, may_decide=access.edit,
        ))

        async def _on_live_change(_match_id, _change_type) -> None:
            """Re-read the queue when anything about a match changes elsewhere.

            Its own subscription rather than the table's ``on_rows_changed``,
            which the other two strips use: those summarise the *visible rows*,
            while this one summarises requests. A request can land on a match the
            board's day or state filter is hiding, and ``update_row_by_id``
            returns early for a row that is not on screen — so riding the table
            would leave staff looking at a stale count precisely when a filter
            is narrowing their view.

            ``register_view`` re-enters the captured client, which is what makes
            the tenant resolvable (it falls back to the client stash) and the
            refresh land in the right browser.
            """
            if access.edit:
                reschedule_queue.refresh()

        register_view(_on_live_change)

        # Route through the view's _bg so the tab-switch refresh rebinds the
        # tenant (the selected_tab handler runs in a detached task that lost it).
        def on_tab_selected():
            table_view._bg(table_view.refresh())
        ui.on('selected_tab', lambda e: on_tab_selected() if e.args == 'Schedule' else None)
