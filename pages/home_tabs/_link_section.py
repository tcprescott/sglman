"""Shared 'Connected accounts' profile section.

Challonge, Twitch, and racetime each expose the same link/unlink affordance;
they differ only in the service class, the copy, the ``<provider>_user_id`` /
``<provider>_username`` attribute names, and the OAuth-initiation route. Rather
than one full card per provider (three near-identical cards to scroll past on a
phone), they render together as compact rows inside a single card. Each provider
module supplies a :class:`LinkSectionConfig`.
"""

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from nicegui import ui

from application.tenant_context import is_host_mode
from application.utils.environment import host_oauth_handoff_enabled
from models import User

__all__ = ['LinkSectionConfig', 'render_connected_accounts_section']


@dataclass(frozen=True)
class LinkSectionConfig:
    title: str
    icon: str
    description: str
    link_route: str
    link_button_label: str
    unlinked_message: str
    user_id_attr: str
    username_attr: str
    service_factory: Callable[[], object]


def _render_provider_row(user: User, config: LinkSectionConfig) -> None:
    """One provider row: icon, name, link status, and a link/unlink button."""
    service = config.service_factory()

    @ui.refreshable
    def row() -> None:
        user_id = getattr(user, config.user_id_attr)
        username: Optional[str] = getattr(user, config.username_attr)
        with ui.row().classes('items-center w-full no-wrap gap-3'):
            ui.icon(config.icon, size='sm').classes('icon-primary')
            with ui.column().classes('gap-0 col'):
                ui.label(config.title).classes('text-weight-medium')
                if user_id:
                    with ui.row().classes('items-center gap-1 no-wrap'):
                        ui.icon('check_circle', size='xs').classes('text-positive')
                        ui.label(f'Linked as {username or user_id}') \
                            .classes('text-caption text-grey-7 ellipsis')
                else:
                    ui.label('Not linked').classes('text-caption text-grey-7')
            if user_id:
                ui.button('Unlink', icon='link_off', on_click=unlink) \
                    .props('flat dense color=negative')
            elif is_host_mode() and not host_oauth_handoff_enabled():
                # Design A: the link callback lives on the platform host and can't
                # see this custom domain's cookie; do it from the main site. With
                # HOST_OAUTH_MODE=handoff the link route runs the cross-host handoff
                # and works in place, so the button shows normally (below).
                ui.label('Main site only').classes('text-caption text-grey') \
                    .tooltip('Account linking is available on the main site.')
            else:
                ui.button('Link', icon='link',
                          on_click=lambda: ui.navigate.to(config.link_route)) \
                    .props('flat dense color=primary')

    async def unlink() -> None:
        try:
            await service.unlink_player(user, actor=user)
            ui.notify(config.unlinked_message, color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
        row.refresh()

    row()


async def render_connected_accounts_section(
    user: User, configs: Sequence[LinkSectionConfig]
) -> None:
    """Render the linkable providers together in one 'Connected accounts' card.

    Providers whose integration isn't configured are skipped; if none are
    configured the whole card is omitted.
    """
    active = [c for c in configs if c.service_factory().is_configured()]
    if not active:
        return

    with ui.card().classes('card-full-width'):
        ui.label('Connected accounts').classes('section-title')
        ui.label(
            'Link external accounts to verify your identity and let us find your '
            'bracket and race matches for scheduling.'
        ).classes('text-muted text-caption')
        for i, config in enumerate(active):
            if i:
                ui.separator().classes('q-my-sm')
            _render_provider_row(user, config)
