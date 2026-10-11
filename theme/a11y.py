"""Accessible names for the controls that only draw an icon.

A tooltip is not an accessible name: Quasar renders ``q-tooltip`` only on
hover, so a screen reader landing on an icon-only button heard "button" and
nothing else (the 2026-10 audit found 500+ of them across every page). Nearly
every one of those buttons already carries a tooltip saying what it does, so
:func:`install_tooltip_labels` makes ``Element.tooltip()`` copy that text into
``aria-label`` on any control that has no visible text of its own.

Vue slot templates (``<q-btn ...><q-tooltip>``) can't be reached from here; they
spell ``aria-label`` out, and ``tests/test_a11y_names.py`` holds them to it.
"""

from typing import Any, Callable

from nicegui import ui
from nicegui.element import Element

_installed = False


def _needs_label(element: Element) -> bool:
    if 'aria-label' in element.props:
        return False
    if isinstance(element, ui.button):
        return not (element.text or '').strip()
    return element.props.get('role') in {'button', 'link'}


def install_tooltip_labels() -> None:
    """Make ``.tooltip(text)`` name an otherwise unnamed control. Idempotent."""
    global _installed
    if _installed:
        return
    original: Callable[..., Any] = Element.tooltip

    def tooltip(self: Element, text: str) -> Element:
        if _needs_label(self):
            self.props['aria-label'] = text
        return original(self, text)

    Element.tooltip = tooltip  # type: ignore[method-assign,assignment]
    _installed = True


_KEY_TO_CLICK = (
    "(e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget)"
    " { e.preventDefault(); e.currentTarget.click(); } }"
)


def make_activatable(element: Element, label: str | None = None, *, role: str = 'button') -> Element:
    """Let the keyboard reach and press a clickable non-button element.

    For a card or icon that already has a ``click`` handler: it joins the tab
    order, announces itself as ``role``, and Enter/Space fire the same ``click``
    the mouse does. Pass ``label`` when the element has no text of its own (an
    icon); a card is named by its contents.
    """
    # aria-hidden: a q-icon hides itself from screen readers by default.
    element.props(f'tabindex=0 role={role} aria-hidden=false')
    if label:
        element.props['aria-label'] = label
    element.on('keydown', js_handler=_KEY_TO_CLICK)
    return element


def label_field(label: Element, field: Element) -> Element:
    """Tie a free-standing caption to the input it sits above.

    Filter strips draw their captions as separate labels so the fields stay
    compact; without this a screen reader reads the field with no name.
    Quasar's ``for`` prop becomes the inner control's id, so a real ``<label
    for>`` points at it.
    """
    target = f'{field.html_id}-control'
    field.props['for'] = target
    label.tag = 'label'
    label.props['for'] = target
    return field
