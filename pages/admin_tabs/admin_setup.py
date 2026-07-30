"""Admin Setup tab — the new-community checklist.

Only present while the community is not ready; ``build_admin_tabs`` drops it
once every required step is done, so there is nothing to dismiss.
"""

from typing import List

from nicegui import ui

from application.services import SetupStep
from theme.base import tab_slug
from theme.setup_checklist import render_setup_checklist


def admin_setup_page(steps: List[SetupStep], base_path: str = '/admin') -> None:
    def go(tab: str) -> None:
        # A full navigation rather than a panel switch: the checklist is rendered
        # inside a tab and has no handle on the layout, and re-entering /admin
        # re-derives the steps, which is what the reader wants after completing
        # one.
        ui.navigate.to(f'{base_path}/{tab_slug(tab)}')

    render_setup_checklist(steps, on_go=go)
