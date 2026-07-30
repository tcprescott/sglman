"""Every equipment control that emits to the server is marked for the offline guard.

The equipment surfaces duplicate their button HTML: a desktop ``body-cell-*``
slot and a mobile ``item`` card, with the same actions in both. Marking only one
is the failure mode worth a test — 390×844 is where the audit actually tapped,
and the card is the copy it tapped.

The invariant is mechanical and survives wave 2's relabelling: the number of
``wiz-requires-socket`` marks in a template equals the number of buttons that
``$emit``. A new row action cannot be added without either marking it or breaking
this.
"""

from pages.admin_tabs.admin_equipment import _ACTIONS_CELL, _GRID_CARD
from pages.home_tabs.equipment import _ICON_BTNS, _LABEL_BTNS
from theme.connection import REQUIRES_SOCKET_CLASS

_REGISTER_TEMPLATES = {'body-cell-actions': _ACTIONS_CELL, 'item': _GRID_CARD}
_HOME_BUTTONS = {f'{form}:{event}': html
                 for form, btns in (('icon', _ICON_BTNS), ('label', _LABEL_BTNS))
                 for event, html in btns.items()}


class TestAdminRegister:
    def test_both_copies_mark_every_emitting_button(self):
        for name, template in _REGISTER_TEMPLATES.items():
            emits = template.count("$parent.$emit(")
            marks = template.count(REQUIRES_SOCKET_CLASS)
            assert emits == 5, f'{name}: expected five row actions, found {emits}'
            assert marks == emits, f'{name}: {emits} actions but {marks} marked'

    def test_the_two_copies_offer_the_same_actions(self):
        def events(template: str) -> set:
            import re
            return set(re.findall(r"\$parent\.\$emit\('(\w+)'", template))

        assert events(_ACTIONS_CELL) == events(_GRID_CARD)
        assert events(_ACTIONS_CELL) == {'checkout', 'checkin', 'view', 'edit', 'remove'}


class TestHomeInventory:
    def test_every_button_is_marked(self):
        for name, snippet in _HOME_BUTTONS.items():
            assert REQUIRES_SOCKET_CLASS in snippet, f'{name} is not marked'
            assert snippet.count("$parent.$emit(") == 1

    def test_the_view_button_is_marked_too(self):
        # It looks like a link but is a server round trip: the click emits, and
        # the server answers with an `open` message.
        assert REQUIRES_SOCKET_CLASS in _ICON_BTNS['view']
        assert REQUIRES_SOCKET_CLASS in _LABEL_BTNS['view']

    def test_both_forms_offer_the_same_actions(self):
        assert set(_ICON_BTNS) == set(_LABEL_BTNS) == {'checkout', 'checkin', 'view'}
