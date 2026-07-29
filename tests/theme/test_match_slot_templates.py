"""Every registered match-table slot must be fully substituted Vue.

The column and grid templates are Python strings carrying ``__NAME__``
placeholders that the server fills in at registration time (``__IA__``,
``__CC__``, ``__DID__``, ``__WATCH__``, ``__ACTCLS__``). A placeholder that
escapes substitution does not raise: it renders as literal text, or silently
breaks the Vue expression it sits inside. Python render tests never see it and a
screenshot only shows the damage if that branch happens to be on screen — so the
guard has to be mechanical.
"""

import re

import pytest

from theme.tables.match_grid import render_grid_slot
from theme.tables.match_slots import register_body_slots

PLACEHOLDER = re.compile(r'__[A-Z]+__')

ADMIN_COLUMNS = [
    {'name': 'id', 'label': 'ID', 'field': 'id'},
    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament'},
    {'name': 'scheduled_at', 'label': 'Scheduled At', 'field': 'scheduled_at'},
    {'name': 'state', 'label': 'State', 'field': 'state'},
    {'name': 'players', 'label': 'Players', 'field': 'players'},
    {'name': 'commentators', 'label': 'Commentators', 'field': 'commentators'},
    {'name': 'trackers', 'label': 'Trackers', 'field': 'trackers'},
    {'name': 'stream_room', 'label': 'Stage', 'field': 'stream_room'},
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


@pytest.mark.parametrize('can_crud', [True, False])
@pytest.mark.parametrize('discord_id', ['12345', None])
def test_no_placeholder_survives_body_slot_registration(can_crud, discord_id):
    table = FakeTable()
    register_body_slots(
        table, admin_controls=True, can_crud=can_crud, discord_id=discord_id,
        has_edit=can_crud, want_seed_slot=True, want_state_slot=True,
        want_stream_room_admin=can_crud, want_stream_room_readonly=not can_crud,
    )
    assert table.slots, 'no slots registered — the guard would pass vacuously'
    assert _leaks(table.slots) == {}


@pytest.mark.parametrize('can_crud', [True, False])
@pytest.mark.parametrize('actions_first', [True, False])
@pytest.mark.parametrize('discord_id', ['12345', None])
def test_no_placeholder_survives_grid_slot_registration(can_crud, actions_first, discord_id):
    table = FakeTable()
    render_grid_slot(
        table, ADMIN_COLUMNS, admin_controls=True, can_crud=can_crud,
        discord_id=discord_id, has_edit=can_crud, actions_first=actions_first,
    )
    assert 'item' in table.slots
    assert _leaks(table.slots) == {}


def test_grid_actions_row_sits_under_the_players_when_actions_first():
    table = FakeTable()
    render_grid_slot(
        table, ADMIN_COLUMNS, admin_controls=True, can_crud=False,
        discord_id='1', has_edit=False, actions_first=True,
    )
    tpl = table.slots['item']
    assert tpl.index('mgc-players') < tpl.index('mgc-actions') < tpl.index('mgc-caption')
    assert 'mgc-actions mgc-actions--first row items-center' in tpl


def test_grid_actions_row_stays_last_by_default():
    table = FakeTable()
    render_grid_slot(
        table, ADMIN_COLUMNS, admin_controls=True, can_crud=True,
        discord_id='1', has_edit=True,
    )
    tpl = table.slots['item']
    assert tpl.index('mgc-caption') < tpl.index('mgc-actions')
    assert 'mgc-actions--first' not in tpl
    assert 'class="mgc-actions row items-center"' in tpl


def test_overdue_emphasis_is_mirrored_on_the_mobile_headline():
    """A desktop cell change without its card mirror is the classic regression."""
    table = FakeTable()
    render_grid_slot(
        table, ADMIN_COLUMNS, admin_controls=True, can_crud=True,
        discord_id='1', has_edit=True,
    )
    assert 'props.row.is_overdue' in table.slots['item']

    cells = FakeTable()
    register_body_slots(
        cells, admin_controls=True, can_crud=True, discord_id='1',
    )
    assert 'props.row.is_overdue' in cells.slots['body-cell-scheduled_at']
