

from nicegui import app, ui

from application.services import MatchService
from application.utils.tenant_session import tenant_session_get, tenant_session_set
from theme.dialog.match_sheet import MatchSheet
from theme.help import help_icon
from theme.tables.match import MatchTableView
from theme.tables.match_access import MatchBoardAccess
from theme.tables.match_player_run_sheet import PLAYER_RUN_SHEET_COLUMNS, decorate_player_row
from theme.tables.preferences import TableKeys

#: Session key for the Needs crew switch, namespaced like the board's filters.
NEEDS_CREW_KEY = 'home_schedule:needs_crew'

_CREW_ROLES = ('commentators', 'trackers')


def needs_crew(row: dict) -> bool:
    """Whether a volunteer could usefully sign up on this row.

    Signup still open, and some role the tournament uses has less approved crew
    than it asks for. On an event day the board runs to thirty-plus cards on a
    phone and most of them are already covered or under way; this is the list
    someone who came to commentate is actually looking for.
    """
    if not row.get('crew_signup_open'):
        return False
    wanted = row.get('crew_wanted') or {}
    required = row.get('crew_required') or {}
    for role in _CREW_ROLES:
        if wanted.get(role) is False:
            continue
        approved = sum(1 for c in row.get(role) or [] if isinstance(c, dict) and c.get('approved'))
        if approved < required.get(role, 1):
            return True
    return False


async def schedule():
    match_service = MatchService()

    with ui.column().classes('page-container'):
        # No page title: the Event tab's view switcher directly above already
        # names this view. The line stays because "you can sign up for crew from
        # this board" is not something the table says on its own.
        # One compact line under the view switcher, not a `header-row` +
        # `separator-spacing` stack: that put ~3em of empty band between a
        # one-sentence note and the board it introduces, and on a phone the
        # help icons dropped to their own line stranded in the middle of it.
        with ui.row().classes('wiz-view-note items-center wiz-help-row'):
            ui.label('Every match, and where you can sign up as crew.') \
                .classes('text-muted')
            await help_icon(('schedule-columns', 'Reading the board'), 'match-states')
            needs_crew_switch = ui.switch(
                'Needs crew', value=bool(tenant_session_get(NEEDS_CREW_KEY, False)),
            ).props('dense').tooltip('Only matches still short of commentators or trackers')

        async def get_query():
            return await match_service.get_all_matches_for_schedule()

        # The details sheet holds what the line leaves out (seed, stations,
        # who's confirmed). A spectator's access, so it offers no staff control.
        discord_id = app.storage.user.get('discord_id')
        sheet = MatchSheet(None, access=MatchBoardAccess(),
                           decorate=lambda row: decorate_player_row(row, discord_id))

        view = MatchTableView(
            row_filter=needs_crew if needs_crew_switch.value else None,
            columns=PLAYER_RUN_SHEET_COLUMNS,
            get_query=get_query,
            admin_controls=False,
            table_key=TableKeys.HOME_SCHEDULE,
            storage_key='home_schedule',
            on_rows_changed=sheet.sync,
            layout='player_run_sheet',
            on_open_match=sheet.open,
        )
        sheet.view = view

        async def on_needs_crew(event) -> None:
            tenant_session_set(NEEDS_CREW_KEY, bool(event.value))
            view.row_filter = needs_crew if event.value else None
            await view.refresh()

        needs_crew_switch.on_value_change(on_needs_crew)

        # The view loads itself once its filters are restored (MatchTableView
        # ._initial_load) — kicking a refresh here as well raced that restore and
        # doubled the query fan-out.
