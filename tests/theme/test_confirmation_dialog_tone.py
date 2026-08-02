"""The shared confirmation dialog's button tone.

``ConfirmationDialog`` is used both for genuine deletes and — since the proctor
UX work — for non-destructive lifecycle steps (start a match, confirm a
recorded result). The default must stay ``negative`` so every pre-existing
caller keeps its red button; only a caller that opts in gets another colour.

Rendering the dialog needs a live NiceGUI client, so this locks the constructor
state that ``open()`` reads.
"""

import inspect

import pytest
from nicegui import ui
from nicegui.client import Client
from nicegui.events import ClickEventArguments
from nicegui.page import page

from theme.dialog.confirmation_dialog import ConfirmationDialog


@pytest.fixture
def slot():
    """A client to build into.

    ``ui.dialog()`` needs one, and NiceGUI's implicit fallback client only
    appears when no other test has created one first.
    """
    with Client(page('/')):
        yield


def _click_confirm(dialog: ConfirmationDialog) -> None:
    button = [e for e in dialog.dialog.descendants() if isinstance(e, ui.button)][-1]
    for listener in button._event_listeners.values():
        if listener.type == 'click':
            listener.handler(ClickEventArguments(sender=button, client=button.client))


class TestConfirmationDialogTone:
    def test_default_tone_is_negative(self):
        assert ConfirmationDialog(message='Delete this?').tone == 'negative'

    def test_default_survives_other_kwargs(self):
        dialog = ConfirmationDialog(
            message='Delete this?', confirm_text='Delete', cancel_text='Keep')
        assert dialog.tone == 'negative'

    def test_tone_is_honoured_when_supplied(self):
        assert ConfirmationDialog(message='Start match #1?', tone='primary').tone == 'primary'

    def test_open_colours_the_button_from_tone(self):
        """``open()`` must read ``self.tone`` rather than a hard-coded colour."""
        source = inspect.getsource(ConfirmationDialog.open)
        assert 'color=negative' not in source
        assert 'color={self.tone}' in source


class TestConfirmationDialogTitle:
    """A bare "Confirm" over a body that also starts with "Confirm…" says nothing."""

    def test_default_title_is_confirm(self):
        assert ConfirmationDialog(message='Delete this?').title == 'Confirm'

    def test_title_is_honoured_when_supplied(self):
        dialog = ConfirmationDialog(message='...', title='Confirm match #3')
        assert dialog.title == 'Confirm match #3'

    def test_open_reads_the_title_rather_than_hard_coding_it(self):
        source = inspect.getsource(ConfirmationDialog.open)
        assert "dialog_header('Confirm'" not in source
        assert 'dialog_header(self.title' in source


class TestConfirmationDialogBody:
    """Callers write these messages as ``'\\n\\n'``-separated paragraphs.

    A plain ``ui.label`` collapses every one of them onto a single line, which is
    how "Start match #1?\\n\\nAlice, Bob" rendered as one run-on sentence.
    """

    def test_open_renders_the_message_with_preserved_line_breaks(self):
        source = inspect.getsource(ConfirmationDialog.open)
        assert 'white-space: pre-line' in source


class TestConfirmationDialogCloses:
    """Confirming closes the dialog, whatever the caller's handler does.

    It used to be each caller's job, and the ones that forgot left the question
    on screen over work that had already happened — "Cancel this match?" still
    up after the match was cancelled.
    """

    def test_confirming_closes_the_dialog(self, slot):
        dialog = ConfirmationDialog(message='Cancel this match?', on_confirm=lambda: None)
        dialog.open()
        _click_confirm(dialog)
        assert dialog.dialog.value is False

    def test_confirming_still_runs_the_handler(self, slot):
        calls = []
        dialog = ConfirmationDialog(message='Cancel this match?', on_confirm=lambda: calls.append(1))
        dialog.open()
        _click_confirm(dialog)
        assert calls == [1]

    def test_the_dialog_is_already_closed_when_the_handler_runs(self, slot):
        """Handlers notify and refresh; none of that should race the close."""
        seen = []
        dialog = ConfirmationDialog(message='Delete this?')
        dialog.on_confirm = lambda: seen.append(dialog.dialog.value)
        dialog.open()
        _click_confirm(dialog)
        assert seen == [False]

    def test_a_dialog_without_a_handler_still_closes(self, slot):
        dialog = ConfirmationDialog(message='Nothing to do')
        dialog.open()
        _click_confirm(dialog)
        assert dialog.dialog.value is False
