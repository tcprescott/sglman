"""The new-community setup checklist panel.

Derived state only (:class:`~application.services.TenantSetupService`), so the
panel disappears on its own once the required steps are done. See the
tenant-onboarding plan, design decision 3.
"""

from typing import Callable, List, Optional

from nicegui import ui

from application.services import SetupStep


def render_setup_checklist(
    steps: List[SetupStep],
    on_go: Optional[Callable[[str], None]] = None,
) -> None:
    """Render the checklist. ``on_go`` receives a tab label to switch to."""
    required = [s for s in steps if s.required]
    advisory = [s for s in steps if not s.required]

    with ui.column().classes('page-container-narrow w-full'):
        with ui.row().classes('header-row'):
            ui.label('Set up your community').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'Matches hang off tournaments, and tournaments need players enrolled '
            'in them — so the order is tournament → enrol players → schedule a '
            'match. Work down this list and it will disappear.'
        ).classes('text-caption text-grey')

        with ui.card().classes('w-full'):
            for step in required:
                _render_step(step, on_go)

            if advisory:
                ui.separator().classes('q-my-sm')
                ui.label('Recommended, not required').classes('text-caption text-grey')
                for step in advisory:
                    _render_step(step, on_go)


def _render_step(step: SetupStep, on_go: Optional[Callable[[str], None]]) -> None:
    with ui.row().classes('items-start no-wrap w-full q-py-xs gap-3'):
        ui.icon(
            'check_circle' if step.done else 'radio_button_unchecked',
        ).props(f"size=sm color={'positive' if step.done else 'grey-6'}")
        with ui.column().classes('gap-0 grow'):
            ui.label(step.label).classes('text-weight-medium' if not step.done else 'text-grey')
            if not step.done:
                ui.label(step.hint).classes('text-caption text-grey')
        if not step.done and on_go is not None:
            ui.button(
                step.tab, icon='arrow_forward',
                on_click=lambda _=None, tab=step.tab: on_go(tab),
            ).props('flat dense color=primary')
