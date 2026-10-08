"""FilterMultiSelect: the colour and caption extras survive NiceGUI's rebuilds.

NiceGUI regenerates the option dicts on every ``update()`` and rebuilds the
selected values from bare ``{value, label}`` pairs, so extras patched onto
``props`` once vanish the moment someone picks something. These pin that both
the option list and the chips keep them.
"""

import pytest
from nicegui import ui
from nicegui.client import Client

from theme.pickers import FilterMultiSelect
from theme.tables.mobile_grid import enable_mobile_grid


@pytest.fixture
def slot():
    with Client(lambda: None, request=None):
        yield


def _picker() -> FilterMultiSelect:
    return FilterMultiSelect(
        {11: 'Mods', 22: 'Helpers'},
        label='Discord roles',
        extras={11: {'color': '#ff0000', 'caption': 'Grants Staff'}},
    )


def test_options_carry_extras(slot):
    picker = _picker()
    options = picker.props['options']
    assert options[0] == {'value': 0, 'label': 'Mods', 'color': '#ff0000', 'caption': 'Grants Staff'}
    assert options[1] == {'value': 1, 'label': 'Helpers'}


def test_extras_survive_a_selection_and_an_update(slot):
    picker = _picker()
    picker.value = [11, 22]
    picker.update()
    assert picker.props['options'][0]['color'] == '#ff0000'
    chips = picker.props['model-value']
    assert chips[0]['color'] == '#ff0000'
    assert 'color' not in chips[1]


def test_is_a_filterable_multiselect(slot):
    picker = _picker()
    assert picker.multiple
    assert picker.props.get('use-input')
    assert picker.value == []


def test_selectable_grid_card_has_a_checkbox(slot):
    columns = [{'name': 'name', 'label': 'Name', 'field': 'name'}]
    table = ui.table(columns=columns, rows=[], row_key='name', selection='multiple')
    enable_mobile_grid(table, columns, selectable=True)  # table-prefs: exempt — test table
    assert 'v-model="props.selected"' in table.slots['item'].template


@pytest.mark.parametrize(('new', 'existing', 'expected'), [
    (0, 0, 'hint'),
    (0, 1, 'That mapping already exists.'),
    (0, 4, 'All of these already exist.'),
    (1, 0, 'Adds 1 mapping.'),
    (3, 1, 'Adds 3 mappings; 1 already exists and will be skipped.'),
    (2, 2, 'Adds 2 mappings; 2 already exist and will be skipped.'),
])
def test_bulk_add_summary(new, existing, expected):
    from theme.pickers import bulk_add_summary
    assert bulk_add_summary(new, existing, empty_hint='hint') == expected
