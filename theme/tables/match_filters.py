"""The match board's filter strip: Day, Tournament, Stage, State.

Split out of ``theme/tables/match.py`` the way the grid, the row handlers and
the lifecycle callbacks already were — that module kept running at the
file-length guideline with four concerns still in it. :class:`MatchFiltersMixin`
is composed into ``MatchTableView`` and reaches ``self.display_service``,
``self.storage_key`` and ``self.refresh`` through it.

Every selection is stored per view *and* per tenant (``_skey`` +
``tenant_session_*``): four boards share one session, and a filter change on the
admin Schedule tab used to silently retarget the home schedule board and the
proctor station too.
"""

from datetime import timedelta

from nicegui import ui

from application.utils.tenant_session import tenant_session_get, tenant_session_set
from application.utils.timezone import local_day_bounds, today_local

# Match lifecycle states, and the subset shown by default. Kept as module constants
# so the storage default, the select options, and the "is this filter changed?"
# check in _active_filter_count cannot drift out of sync.
ALL_MATCH_STATES = ['Scheduled', 'Checked In', 'Started', 'Finished', 'Confirmed']
DEFAULT_STATE_FILTER = ['Scheduled', 'Checked In', 'Started']

# Day scopes for the Day filter. The board had no day or now anchor at all, so
# an operator standing at a venue scrolled ~8 screenfuls of phone to find a
# match by eye — the cards carry every detail and nothing narrowed them to the
# day being run. ``ALL_DAYS`` is the default, so nothing is hidden until asked.
ALL_DAYS = 'All dates'
DAY_SCOPES = [ALL_DAYS, 'Today', 'Tomorrow', 'Next 7 days']

#: ``scope -> (days from today for the first day, for the last day)``, inclusive.
_DAY_OFFSETS = {'Today': (0, 0), 'Tomorrow': (1, 1), 'Next 7 days': (0, 6)}


def day_scope_window(scope: str):
    """UTC ``(start, end)`` epoch seconds for a day scope, or ``None`` for all.

    Resolved on the *display* clock — "today" at 21:00 in New York is not today
    in London — and through ``local_day_bounds`` so the window is half-open and
    does not lose its final second.
    """
    offsets = _DAY_OFFSETS.get(scope)
    if offsets is None:
        return None
    first, last = offsets
    today = today_local()
    start, end = local_day_bounds(today + timedelta(days=first), today + timedelta(days=last))
    return start.timestamp(), end.timestamp()


class MatchFiltersMixin:
    """The filter strip, its stored state, and the options it offers."""

    def _skey(self, name: str) -> str:
        """Session key for one of this view's filters.

        Namespaced per view: four boards share one session, and before this a
        filter change on the admin Schedule tab silently retargeted the home
        schedule board and the proctor station too.
        """
        return f'{self.storage_key}:{name}'

    def _stored_or_default_states(self) -> list:
        """This board's opening State selection.

        A stored choice wins; otherwise the board's own default (the admin
        board needs ``Finished`` — that set is its work). Split out of
        ``_setup_ui`` so the precedence is testable without a slot context.
        """
        return tenant_session_get(
            self._skey('state_filter'),
            list(self.default_state_filter or DEFAULT_STATE_FILTER),
        )

    def _refresh_unless_initializing(self) -> None:
        """Reload the table for a *user's* filter change.

        Restoring a stored filter during the initial load also fires these
        handlers, and each one used to schedule its own full reload — three table
        loads per page render instead of one. During initialization the reload is
        left to :meth:`_initial_load`, which runs once after every filter is
        restored (and therefore reads the final filter state).
        """
        if self._initializing:
            return
        self._bg(self.refresh())

    def _on_state_filter_change(self, *_args, **_kwargs):
        # Tenant-scoped: a filter is meaningful only within its own community.
        tenant_session_set(self._skey('state_filter'), self.state_filter.value)
        self._update_filter_badge()
        self._refresh_unless_initializing()

    def _on_day_filter_change(self, *_args, **_kwargs):
        tenant_session_set(self._skey('day_filter'), self.day_filter.value)
        self._update_filter_badge()
        self._refresh_unless_initializing()

    def _on_tournament_filter_change(self, *_args, **_kwargs):
        # Store the tournament ID value (namespaced by tenant — ids are global).
        tenant_session_set(self._skey('tournament_filter'), self.tournament_filter.value)
        self._update_filter_badge()
        self._refresh_unless_initializing()

    def _on_stage_filter_change(self, *_args, **_kwargs):
        # Store the stage ID value (namespaced by tenant — ids are global).
        tenant_session_set(self._skey('stage_filter'), self.stage_filter.value)
        self._update_filter_badge()
        self._refresh_unless_initializing()

    async def _initial_load(self) -> None:
        """Populate the filters, then load the table exactly once.

        The view owns its own first load: callers used to kick a `refresh()` of
        their own after constructing it, which raced the filter restore (the
        table could load before the stored tournament filter was applied) and
        cost an extra query fan-out.
        """
        try:
            await self._load_tournaments()
            await self._load_stages()
        finally:
            self._initializing = False
        await self.refresh()

    def _toggle_filters(self):
        """Show/hide the filter card on mobile; CSS gates ``wiz-filters-open`` to <1024px."""
        self._filters_open = not self._filters_open
        if self._filters_open:
            self.filters_card.classes(add='wiz-filters-open')
        else:
            self.filters_card.classes(remove='wiz-filters-open')

    def _active_filter_count(self) -> int:
        """Number of the three filters set away from this board's own default.

        Compared against ``default_state_filter`` rather than the module
        constant, so a board that legitimately defaults to a different state
        set does not permanently claim its own default is a custom filter.
        """
        count = 0
        if self.tournament_filter and self.tournament_filter.value:
            count += 1
        if self.stage_filter and self.stage_filter.value:
            count += 1
        default_states = set(self.default_state_filter or DEFAULT_STATE_FILTER)
        if self.state_filter and set(self.state_filter.value or []) != default_states:
            count += 1
        if self.day_filter and self.day_filter.value not in (None, ALL_DAYS):
            count += 1
        return count

    def _update_filter_badge(self):
        """Sync the mobile filter-count badge with the current selections."""
        if self.filter_badge is None:
            return
        count = self._active_filter_count()
        self.filter_badge.text = str(count)
        self.filter_badge.set_visibility(count > 0)

    async def _load_tournaments(self):
        """Load all tournament names for the filter using service layer."""
        self.tournaments_list = await self.display_service.get_tournaments_for_filter()
        # A scoped board offers only its own tournaments: the filter is a choice
        # within the scope, and listing the rest invites picking one that yields
        # an empty board for no visible reason.
        if self.scope_tournament_ids is not None:
            allowed = set(self.scope_tournament_ids)
            self.tournaments_list = {
                tid: name for tid, name in self.tournaments_list.items() if tid in allowed
            }
        default_tournament_id = tenant_session_get(self._skey('tournament_filter'), None)
        if self.tournament_filter:
            self.tournament_filter.options = self.tournaments_list
            self.tournament_filter.value = default_tournament_id
            self.tournament_filter.update()
        self._update_filter_badge()

    async def _load_stages(self):
        """Load all stage names for the filter using service layer."""
        self.stages_list = await self.display_service.get_stages_for_filter()
        default_stage_id = tenant_session_get(self._skey('stage_filter'), None)
        if self.stage_filter:
            self.stage_filter.options = self.stages_list
            self.stage_filter.value = default_stage_id
            self.stage_filter.update()
        self._update_filter_badge()


    def _build_filter_bar(self):
        """Render the toggle row and the filter card; returns the two header slots.

        The search box and the preferences gear are rendered into those slots by
        the caller once the table exists — the strip is built first, for visual
        order.
        """
        # Mobile-only filter toggle (CSS hides this row >=1024px, where the card is
        # shown inline; below 1024px the card is collapsed until toggled open).
        with ui.row().classes('wiz-filter-toggle full-width items-center'):
            ui.button('Filters', icon='filter_list', on_click=self._toggle_filters).props('flat color=primary')
            self.filter_badge = ui.badge('0').props('color=primary')
            self.filter_badge.set_visibility(False)
            ui.space()
            ui.button(icon='refresh', on_click=self.refresh).props('flat color=primary round dense').tooltip('Refresh table')

        self.filters_card = ui.card().classes('match-filters-card')
        with self.filters_card:
            with ui.row().classes('match-filter-row'):
                # Day filter, first because it is the coarsest narrowing and
                # the one an operator working a venue reaches for.
                with ui.column().classes('match-filter-column'):
                    ui.label('Day').classes('match-filter-label')
                    self.day_filter = ui.select(
                        options=list(DAY_SCOPES),
                        value=tenant_session_get(self._skey('day_filter'), ALL_DAYS),
                        on_change=self._on_day_filter_change,
                    ).classes('full-width').props('outlined dense')

                with ui.column().classes('match-filter-column'):
                    ui.label('Tournament').classes('match-filter-label')
                    self.tournament_filter = ui.select(
                        options=[],
                        value=None,
                        multiple=True,
                        on_change=self._on_tournament_filter_change
                    ).classes('full-width').props('outlined dense use-chips')

                with ui.column().classes('match-filter-column'):
                    ui.label('Stage').classes('match-filter-label')
                    self.stage_filter = ui.select(
                        options=[],
                        value=None,
                        multiple=True,
                        on_change=self._on_stage_filter_change
                    ).classes('full-width').props('outlined dense use-chips')

                with ui.column().classes('match-filter-column'):
                    ui.label('State').classes('match-filter-label')
                    default_states = self._stored_or_default_states()
                    self.state_filter = ui.select(
                        options=list(ALL_MATCH_STATES),
                        value=default_states,
                        multiple=True,
                        on_change=self._on_state_filter_change
                    ).classes('full-width').props('outlined dense use-chips')

                ui.space()

                # Refresh button, and a placeholder the preferences gear is
                # rendered into once the table exists (the filter strip is built
                # first, for visual order).
                with ui.column().classes('flex-center'):
                    with ui.row().classes('items-center'):
                        search_slot = ui.row().classes('items-center')
                        gear_slot = ui.row().classes('items-center')
                        ui.button(icon='refresh', on_click=self.refresh) \
                            .props('flat color=primary').tooltip('Refresh table')

        return search_slot, gear_slot
