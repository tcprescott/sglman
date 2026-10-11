

from nicegui import ui

from application.services import MatchService
from application.utils.tenant_session import tenant_session_get, tenant_session_set
from theme.help import help_icon
from theme.tables.match import MatchTableView
from theme.tables.match_slots import SEED_SLOT_READONLY, state_readonly_slot
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
        with ui.row().classes('wiz-view-note items-center'):
            ui.label('Every match, and where you can sign up as crew.') \
                .classes('text-muted')
            # Bare icon = "explain this page"; labelled icons = a named topic.
            # Two bare help_outlines side by side are indistinguishable.
            await help_icon('schedule-columns')
            await help_icon('match-states', label='States')
            needs_crew_switch = ui.switch(
                'Needs crew', value=bool(tenant_session_get(NEEDS_CREW_KEY, False)),
            ).props('dense').tooltip('Only matches still short of commentators or trackers')

        columns = [
            {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True},
            {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at',
             'sortable': True},
            {'name': 'state', 'label': 'State', 'field': 'state', 'sortable': True},
            # Not sortable: joined rosters sort on whoever is listed first.
            {'name': 'players', 'label': 'Players', 'field': 'players'},
            # Crew and Watch beside Players: the Sign up buttons are what this
            # board offers a member, and after Stage and Seed they started past
            # the table's right edge at 1440.
            {'name': 'commentators', 'label': 'Commentators', 'field': 'commentators'},
            {'name': 'trackers', 'label': 'Trackers', 'field': 'trackers'},
            {'name': 'watch', 'label': 'Watch', 'field': 'watch'},
            {'name': 'stage', 'label': 'Stage', 'field': 'stage', 'sortable': True},
            {'name': 'generated_seed', 'label': 'Generated Seed', 'field': 'generated_seed',
             'sortable': True},
        ]

        async def get_query():
            return await match_service.get_all_matches_for_schedule()

        extra_slots = {
            'body-cell-state': state_readonly_slot(scheduled_detailed=True),
            'body-cell-generated_seed': SEED_SLOT_READONLY,
        }

        view = MatchTableView(
            row_filter=needs_crew if needs_crew_switch.value else None,
            columns=columns,
            get_query=get_query,
            admin_controls=False,
            table_key=TableKeys.HOME_SCHEDULE,
            extra_slots=extra_slots,
            grid_breakpoint='lt.lg',
            storage_key='home_schedule',
        )

        async def on_needs_crew(event) -> None:
            tenant_session_set(NEEDS_CREW_KEY, bool(event.value))
            view.row_filter = needs_crew if event.value else None
            await view.refresh()

        needs_crew_switch.on_value_change(on_needs_crew)

        # The view loads itself once its filters are restored (MatchTableView
        # ._initial_load) — kicking a refresh here as well raced that restore and
        # doubled the query fan-out.
