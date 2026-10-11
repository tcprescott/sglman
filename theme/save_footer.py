"""A card's own Save bar, shown only once something in the card has changed.

The old Settings page had one Save at the bottom that wrote a dozen unrelated
values, so fixing a typo in the reminder lead also rewrote the event dates, and
a bad hour on day three refused to save the player limit. Each settings card
now owns its values and its Save, and the bar appears only when there is
something to save.
"""

from typing import Awaitable, Callable

from nicegui import ui
from nicegui.elements.mixins.value_element import ValueElement


class SaveFooter:
    """The footer row of a ``section_panel``; build it inside the panel."""

    def __init__(
        self,
        on_save: Callable[[], Awaitable[bool]],
        *,
        label: str = 'Save',
        enabled: bool = True,
    ) -> None:
        self._on_save = on_save
        with ui.row().classes('wiz-panel__foot items-center no-wrap') as self.row:
            self._hint = ui.label('').classes('wiz-panel__foot-hint')
            ui.space()
            self.button = ui.button(label, on_click=self._save).props('color=primary unelevated no-caps')
        self._enabled = enabled
        # Hidden until there is something to save: a row of greyed-out Save
        # buttons down a page of cards reads as a form that is broken.
        self.row.set_visibility(False)

    def watch(self, *elements: ValueElement) -> 'SaveFooter':
        """Light the button when any of ``elements`` changes value."""
        for element in elements:
            element.on_value_change(lambda _e: self.mark_dirty())
        return self

    def mark_dirty(self) -> None:
        if self._enabled:
            self.row.set_visibility(True)
            self._hint.text = 'Unsaved changes'

    def mark_clean(self) -> None:
        self.row.set_visibility(False)

    async def _save(self) -> None:
        """``on_save`` returns whether it saved; a refusal keeps the edits live."""
        self.button.props('loading')
        try:
            saved = await self._on_save()
        finally:
            self.button.props(remove='loading')
        if saved:
            self.mark_clean()
