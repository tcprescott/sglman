"""Shared 'Link <provider> account' profile section.

The Challonge, Twitch, and racetime profile sections were 47-48 line clones that
differed only in the service class, the copy, the ``<provider>_user_id`` /
``<provider>_username`` attribute names, and the initiation route. This module
holds the one rendering; each provider module supplies a :class:`LinkSectionConfig`.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from nicegui import ui

from application.tenant_context import is_host_mode
from models import User

__all__ = ['LinkSectionConfig', 'render_link_section']


@dataclass(frozen=True)
class LinkSectionConfig:
    title: str
    description: str
    link_route: str
    link_button_label: str
    unlinked_message: str
    user_id_attr: str
    username_attr: str
    service_factory: Callable[[], object]


async def render_link_section(user: User, config: LinkSectionConfig) -> None:
    service = config.service_factory()
    if not service.is_configured():
        return

    with ui.card().classes('card-full-width'):
        ui.label(config.title).classes('section-title')
        ui.label(config.description).classes('text-caption text-grey-7')

        @ui.refreshable
        def status() -> None:
            user_id = getattr(user, config.user_id_attr)
            username: Optional[str] = getattr(user, config.username_attr)
            if user_id:
                with ui.row().classes('items-center'):
                    ui.icon('link', color='positive')
                    ui.label(f"Linked as {username or user_id}").classes('text-bold')
                ui.button('Unlink', icon='link_off', on_click=unlink).props('flat color=negative')
            else:
                ui.label('Not linked.').classes('text-muted')
                if is_host_mode():
                    # The link flow's callback is on the platform host and can't
                    # see this custom domain's cookie; do it from the main site.
                    ui.label(
                        'Account linking is available on the main site.'
                    ).classes('text-caption text-grey')
                else:
                    ui.button(
                        config.link_button_label, icon='link',
                        on_click=lambda: ui.navigate.to(config.link_route),
                    ).props('color=primary')

        async def unlink() -> None:
            try:
                await service.unlink_player(user, actor=user)
                ui.notify(config.unlinked_message, color='positive')
            except ValueError as e:
                ui.notify(str(e), color='warning')
            status.refresh()

        status()
