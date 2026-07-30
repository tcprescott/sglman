"""The shared confirmation dialog's button tone.

``ConfirmationDialog`` is used both for genuine deletes and — since the proctor
UX work — for non-destructive lifecycle steps (start a match, confirm a
recorded result). The default must stay ``negative`` so every pre-existing
caller keeps its red button; only a caller that opts in gets another colour.

Rendering the dialog needs a live NiceGUI client, so this locks the constructor
state that ``open()`` reads.
"""

import inspect

from theme.dialog.confirmation_dialog import ConfirmationDialog


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
