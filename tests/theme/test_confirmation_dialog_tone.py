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
