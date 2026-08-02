"""Every registered match-table slot must be fully substituted Vue.

The column and grid templates are Python strings carrying ``__NAME__``
placeholders that the server fills in at registration time (``__IA__``, the
per-capability flags, ``__DID__``, ``__WATCH__``, ``__ACTCLS__``). A placeholder that
escapes substitution does not raise: it renders as literal text, or silently
breaks the Vue expression it sits inside. Python render tests never see it and a
screenshot only shows the damage if that branch happens to be on screen — so the
guard has to be mechanical.
"""

import pathlib
import re

import pytest

from theme.tables.match_access import MatchBoardAccess
from theme.tables.match_grid import render_grid_slot
from theme.tables.match_slots import register_body_slots

STAFF = MatchBoardAccess.for_roles(is_staff=True)
PROCTOR = MatchBoardAccess.for_roles(is_proctor=True)
COORDINATOR = MatchBoardAccess.for_roles(is_crew_coordinator=True)
STREAM_MANAGER = MatchBoardAccess.for_roles(is_stream_manager=True)

PLACEHOLDER = re.compile(r'__[A-Z]+__')

ADMIN_COLUMNS = [
    {'name': 'id', 'label': 'ID', 'field': 'id'},
    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
    {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
    {'name': 'state', 'label': 'State', 'field': 'state'},
    {'name': 'players', 'label': 'Players', 'field': 'players'},
    {'name': 'commentators', 'label': 'Commentators', 'field': 'commentators'},
    {'name': 'trackers', 'label': 'Trackers', 'field': 'trackers'},
    {'name': 'stage', 'label': 'Stage', 'field': 'stage'},
    {'name': 'generated_seed', 'label': 'Seed', 'field': 'seed'},
    {'name': 'watch', 'label': '', 'field': 'watch'},
]


class FakeTable:
    """Just enough of ``ui.table`` to capture ``add_slot`` calls."""

    def __init__(self):
        self.slots = {}

    def add_slot(self, name, template):
        self.slots[name] = template


def _leaks(slots) -> dict:
    return {name: PLACEHOLDER.findall(tpl) for name, tpl in slots.items()
            if PLACEHOLDER.search(tpl)}


@pytest.mark.parametrize('access', [STAFF, PROCTOR, COORDINATOR, STREAM_MANAGER,
                                    MatchBoardAccess()])
@pytest.mark.parametrize('discord_id', ['12345', None])
def test_no_placeholder_survives_body_slot_registration(access, discord_id):
    table = FakeTable()
    register_body_slots(
        table, admin_controls=True, access=access, discord_id=discord_id,
        has_edit=access.edit, want_seed_slot=access.run,
        want_seed_readonly=not access.run, want_state_slot=True,
        want_stage_admin=access.assign_stream,
        want_stage_readonly=not access.assign_stream,
    )
    assert table.slots, 'no slots registered — the guard would pass vacuously'
    assert _leaks(table.slots) == {}


@pytest.mark.parametrize('access', [STAFF, PROCTOR, COORDINATOR, STREAM_MANAGER,
                                    MatchBoardAccess()])
@pytest.mark.parametrize('actions_first', [True, False])
@pytest.mark.parametrize('discord_id', ['12345', None])
def test_no_placeholder_survives_grid_slot_registration(access, actions_first, discord_id):
    table = FakeTable()
    render_grid_slot(
        table, ADMIN_COLUMNS, admin_controls=True, access=access,
        discord_id=discord_id, has_edit=access.edit, actions_first=actions_first,
    )
    assert 'item' in table.slots
    assert _leaks(table.slots) == {}


def test_grid_actions_row_sits_under_the_players_when_actions_first():
    table = FakeTable()
    render_grid_slot(
        table, ADMIN_COLUMNS, admin_controls=True, access=PROCTOR,
        discord_id='1', has_edit=False, actions_first=True,
    )
    tpl = table.slots['item']
    assert tpl.index('mgc-players') < tpl.index('mgc-actions') < tpl.index('mgc-caption')
    assert 'mgc-actions mgc-actions--first row items-center' in tpl


def test_grid_actions_row_stays_last_by_default():
    table = FakeTable()
    render_grid_slot(
        table, ADMIN_COLUMNS, admin_controls=True, access=STAFF,
        discord_id='1', has_edit=True,
    )
    tpl = table.slots['item']
    assert tpl.index('mgc-caption') < tpl.index('mgc-actions')
    assert 'mgc-actions--first' not in tpl
    assert 'class="mgc-actions row items-center"' in tpl


EDIT_RESULT_EMIT = "$parent.$emit('edit_result'"


def _guard_on(template: str, emit: str) -> str:
    """The ``v-if`` expression the given emit sits under, post-substitution.

    The server bakes each capability flag down to ``true``/``false`` rather than
    dropping the markup, so "who is this control for?" cannot be answered by
    asking whether the string is present — only by reading its guard.
    """
    head = template[:template.index(emit)]
    start = head.rindex('v-if="') + len('v-if="')
    return head[start:head.index('"', start)]


def _state_and_grid_slots(access=STAFF):
    """The desktop State cell and the mobile card, as one viewer sees them."""
    cells = FakeTable()
    register_body_slots(
        cells, admin_controls=True, access=access, discord_id='1',
        want_state_slot=True,
    )
    grid = FakeTable()
    render_grid_slot(
        grid, ADMIN_COLUMNS, admin_controls=True, access=access,
        discord_id='1', has_edit=access.edit,
    )
    return cells.slots['body-cell-state'], grid.slots['item']


def test_both_layouts_offer_to_change_a_recorded_winner():
    """A desktop-only control is invisible to every phone on the floor."""
    state_cell, card = _state_and_grid_slots()
    assert EDIT_RESULT_EMIT in state_cell
    assert EDIT_RESULT_EMIT in card
    # The mobile mirror must be readable without a hover, so it is labelled.
    assert 'Change Winner' in card


@pytest.mark.parametrize('access,allowed', [
    (STAFF, True), (PROCTOR, False), (COORDINATOR, False), (STREAM_MANAGER, False),
])
def test_changing_a_recorded_winner_needs_the_confirm_capability(access, allowed):
    """A proctor records the result; correcting it is the admin's call.

    Pinned per role rather than per boolean: ``can_confirm_match`` is the gate
    the service applies, and three of the four roles the board admits fail it.
    """
    assert access.confirm is allowed
    for template in _state_and_grid_slots(access):
        guard = _guard_on(template, EDIT_RESULT_EMIT)
        assert ('false' in guard) != allowed, (
            f'edit_result is guarded by {guard!r} for {access}'
        )


def test_both_layouts_show_the_dispute_flag():
    """The whole point of the flag is that an admin notices it on any device."""
    state_cell, card = _state_and_grid_slots()
    for template in (state_cell, card):
        assert 'props.row.needs_review' in template
        assert 'Needs review' in template


def test_what_the_flag_means_is_text_on_mobile_and_a_tooltip_on_desktop():
    """A tooltip needs a hover, and a phone has no pointer to hover with."""
    state_cell, card = _state_and_grid_slots()

    note_cell = state_cell[state_cell.index('needs_review'):]
    assert '<q-tooltip>The proctor flagged this result.' in note_cell

    review_block = card[card.index('needs_review'):]
    review_block = review_block[:review_block.index('</div>')]
    assert 'The proctor flagged this result.' in review_block
    assert 'q-tooltip' not in review_block


def test_the_dispute_flag_is_gated_on_no_capability():
    """A proctor set it; they must be able to see that they did.

    Reading the guard rather than the presence of the markup, for the reason
    ``_guard_on`` documents: a capability flag bakes down to a literal, so a
    gated control is still *there* in the template for everyone.
    """
    for access in (STAFF, PROCTOR, COORDINATOR, STREAM_MANAGER):
        for template in _state_and_grid_slots(access):
            guard = re.search(r'v-if="([^"]*needs_review[^"]*)"', template)
            assert guard is not None
            assert guard.group(1) == 'props.row.needs_review'


CONFIRM_EMIT = "$parent.$emit('confirm'"


def _own_guard(template: str, emit: str) -> str:
    """The ``v-if`` *or* ``v-else-if`` on the element carrying ``emit``.

    ``_guard_on`` only finds a plain ``v-if``: the grid's action row chains its
    lifecycle buttons with ``v-else-if``, which does not contain the substring
    ``v-if="``, so searching for that walks back past the whole chain.
    """
    head = template[:template.index(emit)]
    start = max(head.rfind('v-if="'), head.rfind('v-else-if="'))
    assert start != -1, f'no guard precedes {emit!r}'
    start = head.index('"', start) + 1
    return head[start:head.index('"', start)]


def test_confirm_is_offered_only_when_a_winner_is_recorded():
    """A Finished match with no result cannot be confirmed — the service refuses it.

    Offering the button anyway teaches the admin to click it and read an error,
    so both layouts gate it on ``has_result`` and say what is missing instead.
    """
    for template in _state_and_grid_slots():
        guard = _own_guard(template, CONFIRM_EMIT)
        assert 'props.row.has_result' in guard, (
            f'confirm is guarded by {guard!r}, which ignores whether a result exists'
        )
        assert 'No result' in template


def test_a_result_less_finished_match_leads_with_recording_one():
    """The pencil is the control that fixes it, so it stops being a bare icon.

    Same label on both layouts — a desktop/mobile wording split is a drift the
    mirrors have no reason to carry.
    """
    for template in _state_and_grid_slots():
        assert 'Record Winner' in template


def test_a_seed_can_only_be_rolled_while_it_can_still_help():
    """One roll per match: burning it early or after the finish is not recoverable.

    A bracket row with no players yet would DM the seed to nobody and leave the
    real players unable to roll another; past Finished there is nothing to seed.
    """
    cells = FakeTable()
    register_body_slots(
        cells, admin_controls=True, access=STAFF, discord_id='1', want_seed_slot=True,
    )
    grid = FakeTable()
    render_grid_slot(
        grid, ADMIN_COLUMNS, admin_controls=True, access=STAFF,
        discord_id='1', has_edit=True,
    )
    for template in (cells.slots['body-cell-generated_seed'], grid.slots['item']):
        guard = _guard_on(template, "$parent.$emit('roll'")
        assert 'props.row.players.length' in guard, f'roll is guarded by {guard!r}'
        assert "'Finished', 'Confirmed'" in guard, f'roll is guarded by {guard!r}'


def test_assigning_stations_is_labelled_on_both_layouts():
    """The proctor board is read on a tablet, where a tooltip never opens."""
    cells = FakeTable()
    register_body_slots(
        cells, admin_controls=True, access=STAFF, discord_id='1',
    )
    grid = FakeTable()
    render_grid_slot(
        grid, ADMIN_COLUMNS, admin_controls=True, access=STAFF,
        discord_id='1', has_edit=True,
    )
    players_cell = cells.slots['body-cell-players']
    # The button's own markup, so the comment above it explaining the icon it
    # replaced doesn't satisfy the assertion.
    btn_start = players_cell.rindex('<q-btn', 0, players_cell.index("$emit('assign_stations'"))
    stations_btn = players_cell[btn_start:]
    stations_btn = stations_btn[:stations_btn.index('</q-btn>')]
    assert 'switch_access_shortcut' not in stations_btn
    assert 'icon="chair"' in stations_btn
    assert 'Stations' in stations_btn
    assert 'Assign Stations' in grid.slots['item']


def test_overdue_emphasis_is_mirrored_on_the_mobile_headline():
    """A desktop cell change without its card mirror is the classic regression."""
    table = FakeTable()
    render_grid_slot(
        table, ADMIN_COLUMNS, admin_controls=True, access=STAFF,
        discord_id='1', has_edit=True,
    )
    assert 'props.row.is_overdue' in table.slots['item']

    cells = FakeTable()
    register_body_slots(
        cells, admin_controls=True, access=STAFF, discord_id='1',
    )
    assert 'props.row.is_overdue' in cells.slots['body-cell-scheduled_at']


# --- The capability split ---------------------------------------------------
#
# Each control below has one gate in ``AuthService`` and used to have a different
# one on the board. These pin the pairing per role, on both layouts, because a
# desktop-only fix is invisible to every phone on the floor.

def _players_and_crew(access):
    cells = FakeTable()
    register_body_slots(
        cells, admin_controls=True, access=access, discord_id='1',
    )
    grid = FakeTable()
    render_grid_slot(
        grid, ADMIN_COLUMNS, admin_controls=True, access=access,
        discord_id='1', has_edit=access.edit,
    )
    return cells.slots, grid.slots['item']


@pytest.mark.parametrize('access,allowed', [
    (STAFF, True), (PROCTOR, True), (COORDINATOR, False), (STREAM_MANAGER, False),
])
def test_running_a_match_needs_the_run_capability(access, allowed):
    """Check In / Start / Finish / Stations are ``can_run_match``, which admits a
    proctor and refuses a coordinator and a stream manager alike."""
    assert access.run is allowed
    state_cell, card = _state_and_grid_slots(access)
    cells, _grid = _players_and_crew(access)

    for template, emit in ((state_cell, "$parent.$emit('seat'"),
                           (card, "$parent.$emit('seat'"),
                           (cells['body-cell-players'], "$emit('assign_stations'")):
        guard = _own_guard(template, emit)
        assert ('false' in guard) != allowed, (
            f'{emit} is guarded by {guard!r} for {access}'
        )


@pytest.mark.parametrize('access,allowed', [
    (STAFF, True), (PROCTOR, False), (COORDINATOR, True), (STREAM_MANAGER, False),
])
def test_approving_crew_needs_the_crew_capability(access, allowed):
    """``can_approve_crew`` is the one gate a crew coordinator passes.

    Before the split the toggle hung off the board's crud boolean, so the single
    action the role exists for was the single action it could not reach.
    """
    assert access.approve_crew is allowed
    cells, card = _players_and_crew(access)
    for template, emit in (
        (cells['body-cell-commentators'], "$parent.$emit('toggle_commentator'"),
        (cells['body-cell-trackers'], "$parent.$emit('toggle_tracker'"),
        (card, "$parent.$emit('toggle_commentator'"),
        (card, "$parent.$emit('toggle_tracker'"),
    ):
        guard = _own_guard(template, emit)
        assert ('false' in guard) != allowed, (
            f'the crew toggle is guarded by {guard!r} for {access}'
        )


@pytest.mark.parametrize('access,allowed', [
    (STAFF, True), (PROCTOR, False), (COORDINATOR, False), (STREAM_MANAGER, True),
])
def test_assigning_a_stage_needs_the_stream_capability(access, allowed):
    """``can_assign_match_stream`` names STREAM_MANAGER in its own docstring."""
    assert access.assign_stream is allowed
    _cells, card = _players_and_crew(access)
    guard = _own_guard(card, "$parent.$emit('set_stage'")
    assert ('false' in guard) != allowed, (
        f'the Stage select is guarded by {guard!r} for {access}'
    )


def test_a_viewer_who_can_run_nothing_still_reads_the_state():
    """The cell carries the chips and timestamps, not only the buttons.

    Dropping the slot for a coordinator would fall back to Quasar's default cell
    and lose the dispute flag, the Awaiting-confirmation chip and every
    timestamp — a board stripped of its meaning rather than of its controls.
    """
    state_cell, _card = _state_and_grid_slots(COORDINATOR)
    assert 'props.row.state_timestamp' in state_cell
    assert 'Awaiting confirmation' in state_cell
    assert 'Needs review' in state_cell
    assert "$parent.$emit('seat'" not in state_cell or 'false' in _own_guard(
        state_cell, "$parent.$emit('seat'")


# --- One read-only state cell, not three -----------------------------------

def test_the_read_only_cells_have_callers():
    """``state_readonly_slot`` and ``SEED_SLOT_READONLY`` were written *"so pages
    can drop their inline templates"* and then had zero callers, while the home
    schedule and the player dashboard each kept their own copy — three
    divergent copies of one cell, in a layer with no render coverage."""
    from theme.tables.match_slots import SEED_SLOT_READONLY, state_readonly_slot

    for path in ('pages/home_tabs/schedule.py', 'pages/home_tabs/player.py'):
        src = pathlib.Path(path).read_text()
        assert 'state_readonly_slot(' in src, path
        assert 'SEED_SLOT_READONLY' in src, path
        # And no hand-rolled replacement crept back in beside it.
        assert "'body-cell-state': '''" not in src, path
        assert "'body-cell-generated_seed': '''" not in src, path

    assert state_readonly_slot(scheduled_detailed=True) != state_readonly_slot(
        scheduled_detailed=False), 'the two variants must still differ'
    assert SEED_SLOT_READONLY.count('<q-btn') == 0, 'the read-only cell rolls nothing'


def test_the_two_scheduled_variants_differ_only_in_their_scheduled_branch():
    """Everything above ``Scheduled`` must match byte for byte, which is the
    whole reason one function serves both boards."""
    from theme.tables.match_slots import state_readonly_slot

    detailed = state_readonly_slot(scheduled_detailed=True)
    plain = state_readonly_slot(scheduled_detailed=False)
    marker = '<!-- Scheduled state -->'
    assert detailed[:detailed.index(marker)] == plain[:plain.index(marker)]


class TestTheStageCell:
    """The Stage cell reads as text and becomes a dropdown on click."""

    def test_it_is_borderless_with_no_floating_label(self):
        from theme.tables.match_slots import STAGE_ADMIN_SLOT
        assert 'borderless' in STAGE_ADMIN_SLOT
        assert 'outlined' not in STAGE_ADMIN_SLOT
        assert 'label="Stage"' not in STAGE_ADMIN_SLOT

    def test_no_stage_is_an_option_rather_than_a_clear_button(self):
        # "None" is one of the answers, not the absence of one — and a clear
        # affordance that appears only once something is chosen cannot be found
        # by someone looking for it.
        from theme.tables.match_grid import _STREAM_DETAIL
        from theme.tables.match_slots import STAGE_ADMIN_SLOT
        assert 'clearable' not in STAGE_ADMIN_SLOT
        assert 'clearable' not in _STREAM_DETAIL

    def test_the_options_lead_with_no_stage_then_candidate(self):
        from theme.tables.match import MatchTableView

        view = object.__new__(MatchTableView)
        view.on_set_stage = lambda *_: None
        view.stages_list = {7: 'Stage 1', 8: 'Stage 2'}
        options = view._stage_options()
        assert options[0] == {'label': 'No Stage', 'value': None}
        assert options[1]['label'] == 'Candidate'
        assert [o['label'] for o in options[2:]] == ['Stage 1', 'Stage 2']

    def test_a_board_that_cannot_set_a_stage_gets_no_options(self):
        from theme.tables.match import MatchTableView

        view = object.__new__(MatchTableView)
        view.on_set_stage = None
        assert view._stage_options() is None


class TestStreamVolunteering:
    """A player's offer is advisory, and every surface has to say so.

    The toggle sits in the same row as the Stage column, so a bare icon reads as
    claiming a stage. These pin the copy that stops it reading that way.
    """

    def _volunteer_cell(self, discord_id='12345'):
        table = FakeTable()
        register_body_slots(
            table, admin_controls=False, access=MatchBoardAccess(),
            discord_id=discord_id,
        )
        return table.slots.get('body-cell-stream_volunteer')

    def test_the_cell_exists_only_for_a_logged_in_viewer(self):
        assert self._volunteer_cell() is not None
        assert self._volunteer_cell(discord_id=None) is None

    def test_only_a_player_in_the_match_gets_the_toggle(self):
        """The service refuses anyone else, so offering it teaches a refusal."""
        cell = self._volunteer_cell()
        guard = _guard_on(cell, "$parent.$emit('toggle_stream_volunteer'")
        assert "props.row.players.some(p => p.discord_id == '12345')" in guard

    def test_the_toggle_says_it_does_not_book_a_stage(self):
        assert "doesn't book a stage" in self._volunteer_cell()

    def test_a_non_player_reads_the_count_instead(self):
        cell = self._volunteer_cell()
        assert 'props.row.stream_volunteers.length' in cell
        assert 'Advisory only.' in cell

    def test_the_mobile_card_names_the_offer_as_advisory(self):
        table = FakeTable()
        render_grid_slot(
            table, [*ADMIN_COLUMNS,
                    {'name': 'stream_volunteer', 'label': 'Stream',
                     'field': 'stream_volunteer'}],
            admin_controls=False, access=MatchBoardAccess(), discord_id='12345',
            has_edit=False,
        )
        tpl = table.slots['item']
        assert 'advisory, not a booking' in tpl
        assert "$parent.$emit('toggle_stream_volunteer'" in tpl

    def test_a_board_without_the_column_gets_no_mobile_toggle(self):
        table = FakeTable()
        render_grid_slot(
            table, ADMIN_COLUMNS, admin_controls=False,
            access=MatchBoardAccess(), discord_id='12345', has_edit=False,
        )
        guard = _guard_on(
            table.slots['item'], "$parent.$emit('toggle_stream_volunteer'",
        )
        assert guard.startswith('false')

    def test_offering_never_writes_the_stream_candidate_flag(self):
        """Staff's decision stays staff's — the two live in different places."""
        import inspect

        from theme.tables import match_handlers

        src = inspect.getsource(match_handlers.MatchTableHandlersMixin._handle_toggle_stream_volunteer)
        assert 'is_stream_candidate' not in src
        assert 'does not guarantee' in src


def test_request_match_is_offered_only_where_a_request_can_be_made():
    """A bracket-run community has nothing to request, and the dialog's own dead
    end ("schedule your matchup from Your Schedule instead") is the wrong place
    to learn that — the button should not have been there.

    Pinned at the source, because the decision is a page-build-time argument to
    ``MatchTableView`` and the button lives behind ``if self.submit_match_callback``.
    """
    src = pathlib.Path('pages/home_tabs/player.py').read_text()
    assert 'list_player_requestable(viewer)' in src
    assert 'submit_match_callback=submit_match if can_request else None' in src

    table_src = pathlib.Path('theme/tables/match.py').read_text()
    assert 'if self.submit_match_callback:' in table_src


def test_the_offer_disappears_once_the_match_is_under_way():
    """Offering is refused after the start, so a board that keeps offering it
    only teaches a refusal. Withdrawing stays available — a player who changes
    their mind must not be stuck with a request they cannot unsay."""
    from theme.tables.match_slots import STREAM_VOLUNTEER_ACTIONABLE

    table = FakeTable()
    register_body_slots(
        table, admin_controls=False, access=MatchBoardAccess(), discord_id='7',
    )
    guard = _guard_on(
        table.slots['body-cell-stream_volunteer'],
        "$parent.$emit('toggle_stream_volunteer'",
    )
    assert STREAM_VOLUNTEER_ACTIONABLE in guard
    assert 'props.row._stream_volunteer' in STREAM_VOLUNTEER_ACTIONABLE
    assert "['Scheduled', 'Checked In'].includes(props.row.state)" in STREAM_VOLUNTEER_ACTIONABLE

    # And the mobile card reads the same expression rather than a second copy.
    grid = FakeTable()
    render_grid_slot(
        grid, [*ADMIN_COLUMNS,
               {'name': 'stream_volunteer', 'label': 'Stream',
                'field': 'stream_volunteer'}],
        admin_controls=False, access=MatchBoardAccess(), discord_id='7',
        has_edit=False,
    )
    assert STREAM_VOLUNTEER_ACTIONABLE in grid.slots['item']
