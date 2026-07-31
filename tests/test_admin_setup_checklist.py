"""Which tab a community's admin area opens on.

The audit's finding was that a brand-new community lands on Schedule Management,
whose Create Match cannot succeed — there is no tournament to pick. The Setup tab
is prepended while required steps are outstanding and ``BaseLayout`` defaults to
``tabs[0]``, so this pins both halves: that it is first while unready, and that
it disappears (restoring Schedule) once the community is set up.
"""

from application.services.tenant_setup_service import SetupStep
from pages.admin import AdminAccess, build_admin_tabs


def _steps(*, ready: bool):
    return [
        SetupStep(key='staff', label='Staff', done=True, hint='', tab='Users', required=True),
        SetupStep(key='tournament', label='Tournament', done=ready, hint='', tab='Tournaments', required=True),
        SetupStep(key='enrolment', label='Enrolment', done=ready, hint='', tab='Tournaments', required=True),
        # Advisory and never done, so it can never be what keeps Setup on screen.
        SetupStep(key='stream_room', label='Stage', done=False, hint='', tab='Stream Rooms', required=False),
    ]


STAFF = AdminAccess(is_staff=True)


def _labels(tabs):
    return [t['label'] for t in tabs]


def test_setup_tab_is_present_and_default_for_an_unready_tenant():
    tabs = build_admin_tabs(STAFF, set(), {}, _steps(ready=False))
    assert _labels(tabs)[0] == 'Setup'


def test_setup_tab_is_absent_once_required_steps_are_done():
    tabs = build_admin_tabs(STAFF, set(), {}, _steps(ready=True))
    assert 'Setup' not in _labels(tabs)


def test_schedule_is_still_the_default_for_a_ready_tenant():
    tabs = build_admin_tabs(STAFF, set(), {}, _steps(ready=True))
    assert _labels(tabs)[0] == 'Schedule'


def test_outstanding_advisory_steps_do_not_keep_the_tab_on_screen():
    steps = _steps(ready=True)
    assert any(s.required is False and s.done is False for s in steps)
    assert 'Setup' not in _labels(build_admin_tabs(STAFF, set(), {}, steps))


def test_no_setup_steps_means_no_setup_tab():
    # The callers that do not load a checklist (none today) must not crash or
    # sprout an empty panel.
    assert 'Setup' not in _labels(build_admin_tabs(STAFF, set(), {}, None))


def test_the_checklist_is_not_offered_to_a_non_admin_role():
    # A stream manager sees the admin area but cannot create tournaments or
    # grant staff, so a checklist of things they cannot do is noise.
    tabs = build_admin_tabs(AdminAccess(is_stream_manager=True), set(), {}, _steps(ready=False))
    assert 'Setup' not in _labels(tabs)
    # Schedule is theirs because assigning a stage is a match-board action and
    # this is the only board that offers it; Stream Rooms manages the venues.
    assert _labels(tabs) == ['Schedule', 'Stream Rooms']


def test_the_stream_manager_reaches_the_board_with_only_the_stage_control():
    """The role ``assign_stage`` names in its own docstring had no surface.

    Granting the tab is only half of it — the board must offer them the one
    control the service admits and none of the ones it refuses.
    """
    tabs = build_admin_tabs(AdminAccess(is_stream_manager=True), set(), {}, None)
    _fn, _args, kwargs = next(t['content'] for t in tabs if t['label'] == 'Schedule')
    access = kwargs['access']
    assert access.assign_stream is True
    assert not access.edit and not access.run and not access.confirm and not access.approve_crew
    # Community-wide authority, so their board is not narrowed to a tournament set.
    assert kwargs['tournament_ids'] is None


def test_the_crew_coordinators_board_offers_approval_and_nothing_else():
    """The finding this split closes: 37 controls that all refused, and not the one."""
    access_in = AdminAccess(is_crew_coordinator=True, operated_tournament_ids=frozenset({7}))
    tabs = build_admin_tabs(access_in, set(), {}, None)
    _fn, _args, kwargs = next(t['content'] for t in tabs if t['label'] == 'Schedule')
    access = kwargs['access']
    assert access.approve_crew is True
    assert not access.edit and not access.run and not access.confirm and not access.assign_stream
    # And the board is theirs, not the whole community's.
    assert kwargs['tournament_ids'] == [7]


def test_staffs_board_is_not_scoped_to_a_tournament_set():
    tabs = build_admin_tabs(STAFF, set(), {}, None)
    _fn, _args, kwargs = next(t['content'] for t in tabs if t['label'] == 'Schedule')
    assert kwargs['tournament_ids'] is None
    assert kwargs['access'].edit and kwargs['access'].run and kwargs['access'].confirm


def test_setup_tab_carries_the_root_path_so_its_links_survive_a_tenant_prefix():
    tabs = build_admin_tabs(STAFF, set(), {}, _steps(ready=False), '/t/acme/admin')
    _fn, _args, kwargs = tabs[0]['content']
    assert kwargs['base_path'] == '/t/acme/admin'


def test_group_order_is_unchanged_by_the_new_tab():
    tabs = build_admin_tabs(STAFF, set(), {}, _steps(ready=False))
    groups = [t['group'] for t in tabs]
    assert groups == sorted(groups, key=['Operations', 'Online play', 'Community',
                                         'Integrations', 'System'].index)
