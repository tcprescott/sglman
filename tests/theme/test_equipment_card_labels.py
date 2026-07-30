"""The equipment cards say what their buttons do, and Delete stands apart.

The register's mobile card used to end in four icon-only buttons — check-out,
QR, edit, **delete** — explained only by a `q-tooltip`. On a phone a tooltip
never opens, so the audit's operator had four unlabelled circles, one of which
deletes the asset, all a thumb-width apart. This codebase had already settled
the principle for the proctor board ("the proctor reads this board on a tablet,
where a tooltip never opens", `theme/tables/match_slots.py`).

Desktop deliberately stays icon-only: a tooltip does open on a mouse, and the
wide row has no room for four labels.
"""

import re

from pages.admin_tabs.admin_equipment import _ACTIONS_CELL, _GRID_CARD
from pages.home_tabs.equipment import _ICON_BTNS, _LABEL_BTNS


def _labels(template: str) -> set:
    return set(re.findall(r'label="([^"]+)"', template))


class TestRegisterCard:
    def test_every_card_action_carries_visible_text(self):
        assert _labels(_GRID_CARD) == {'Check out', 'Check in', 'Open', 'Edit', 'Delete'}

    def test_no_card_action_relies_on_a_tooltip_alone(self):
        # Every button in the card must have a label; none may be a bare icon.
        buttons = re.findall(r'<q-btn\b[^>]*', _GRID_CARD)
        assert buttons, 'no buttons found in the card'
        for button in buttons:
            assert 'label=' in button, f'icon-only button in the card: {button[:80]}'

    def test_delete_leaves_the_row_the_others_share(self):
        # Delete must not sit in the same flex row as Edit — it gets its own.
        rows = _GRID_CARD.split('<div class="row')
        edit_row = next(r for r in rows if "$emit('edit'" in r)
        assert "$emit('remove'" not in edit_row, 'Delete is adjacent to Edit'

    def test_delete_stays_visually_distinct(self):
        remove = next(b for b in re.findall(r'<q-btn\b[^>]*', _GRID_CARD)
                      if "$emit('remove'" in b or 'Delete' in b)
        assert 'outline' in remove
        assert 'color="negative"' in remove

    def test_desktop_stays_icon_only(self):
        assert _labels(_ACTIONS_CELL) == set()
        assert '<q-tooltip>' in _ACTIONS_CELL


class TestHomeTabCards:
    def test_the_card_form_is_labelled(self):
        assert _labels(''.join(_LABEL_BTNS.values())) == {'Check out', 'Check in', 'View'}

    def test_the_desktop_form_is_not(self):
        assert _labels(''.join(_ICON_BTNS.values())) == set()
        assert all('<q-tooltip>' in html for html in _ICON_BTNS.values())
