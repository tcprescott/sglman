"""A WYSIWYG markdown editor element, built on Tiptap.

Writers see formatted text and a toolbar; the value is markdown. The toolbar
offers only what :mod:`application.content.blocks` can render (bold, italic,
inline code, links, two heading levels, lists and notes), so what someone
formats is what readers get. The saved markdown is still untrusted input:
render it with ``parse_blocks`` + ``theme.help.render.render_blocks``, never
``ui.markdown``.

The Tiptap bundle is vendored in ``dist/`` (MIT; notices in
``dist/THIRD_PARTY_LICENSES.txt``). Rebuild it with ``npm ci && npm run build``
in this directory after changing ``package.json`` or ``src/``.
"""

from typing import Any, Optional

from nicegui.elements.mixins.disableable_element import DisableableElement
from nicegui.elements.mixins.value_element import ValueElement
from nicegui.events import Handler, ValueChangeEventArguments

__all__ = ['MarkdownEditor']


class MarkdownEditor(
    ValueElement[str], DisableableElement,
    component='markdown_editor.js', esm={'wizzrobe-tiptap': 'dist'},
):
    VALUE_PROP: str = 'value'
    LOOPBACK = False

    def __init__(
        self,
        label: Optional[str] = None,
        *,
        value: str = '',
        placeholder: Optional[str] = None,
        compact: bool = False,
        on_change: Optional[Handler[ValueChangeEventArguments[str]]] = None,
    ) -> None:
        super().__init__(value=value or '', on_value_change=on_change)
        if label:
            self._props['label'] = label
        if placeholder:
            self._props['placeholder'] = placeholder
        if compact:
            self._props['compact'] = True

    def _event_args_to_value(self, e: Any) -> str:
        return e.args if isinstance(e.args, str) else ''
