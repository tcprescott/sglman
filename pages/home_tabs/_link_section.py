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
from application.utils.timezone import format_local_date
from models import User
from pages._oauth_link import platform_link_redirect
from theme.dialog.confirmation_dialog import ConfirmationDialog

__all__ = ['LinkSectionConfig', 'render_connected_accounts_section']


@dataclass(frozen=True)
class LinkSectionConfig:
    """Everything the shared row renderer needs for one provider.

    **Every field here must be rendered or deleted.** ``description`` and
    ``link_button_label`` were declared, populated three times and read by
    nothing for the whole life of this section, which is how an audit came to
    praise copy that had never been on a screen.
    """

    title: str
    icon: str
    description: str
    link_route: str
    link_button_label: str
    unlink_button_label: str
    unlinked_message: str
    user_id_attr: str
    username_attr: str
    linked_at_attr: str
    service_factory: Callable[[], object]
    # Only for a provider where unlinking changes more than the row: the body of
    # a confirmation dialog. None means the unlink is cheap and reversible and
    # goes through on one click, which is the right answer for most of them.
    unlink_confirmation: Optional[str] = None


def _render_provider_row(
    user: User, config: LinkSectionConfig, main_site_url: Optional[str] = None,
) -> None:
    """One provider row: icon, name, link status, and a link/unlink button."""
    service = config.service_factory()

    @ui.refreshable
    def row() -> None:
        user_id = getattr(user, config.user_id_attr)
        username: Optional[str] = getattr(user, config.username_attr)
        linked_at = getattr(user, config.linked_at_attr, None)
        with ui.row().classes('items-center w-full no-wrap gap-3'):
            ui.icon(config.icon, size='sm').classes('icon-primary')
            with ui.column().classes('gap-0 col'):
                ui.label(config.title).classes('text-weight-medium')
                if user_id:
                    with ui.row().classes('items-center gap-1 no-wrap'):
                        ui.icon('check_circle', size='xs').classes('text-positive')
                        # A date is what lets someone recognise a link they made
                        # years ago under a provider name they have since changed.
                        # Additive: a row linked before the column existed has none.
                        since = f' on {format_local_date(linked_at)}' if linked_at else ''
                        ui.label(f'Linked as {username or user_id}{since}') \
                            .classes('text-caption text-grey-7 ellipsis')
                else:
                    ui.label('Not linked').classes('text-caption text-grey-7')
                    # Only on the unlinked row: this is where the decision is made,
                    # and three descriptions plus three statuses is a scroll on a
                    # phone. A linked row answers a different question, which the
                    # account name and date above already answer.
                    ui.label(config.description).classes('text-caption text-muted')
            if user_id:
                # The visible label stays short (three rows, one narrow column);
                # the configured full label is what a screen reader announces, so
                # the row stops being three identically-named buttons.
                ui.button('Unlink', icon='link_off', on_click=confirm_unlink) \
                    .props(f'flat dense color=negative aria-label="{config.unlink_button_label}"') \
                    .tooltip(config.unlink_button_label)
            elif is_host_mode() and not host_oauth_handoff_enabled():
                # Design A: the link callback lives on the platform host and can't
                # see this custom domain's cookie; do it from the main site. With
                # HOST_OAUTH_MODE=handoff the link route runs the cross-host handoff
                # and works in place, so the button shows normally (below).
                # Naming a place without going there is a dead end, so this is a
                # link to the platform-host equivalent of this page.
                ui.link('Main site only', main_site_url or '/') \
                    .classes('text-caption') \
                    .tooltip(f'Open your profile on the main site to link {config.title}.')
            else:
                ui.button('Link', icon='link',
                          on_click=lambda: ui.navigate.to(config.link_route)) \
                    .props(f'flat dense color=primary aria-label="{config.link_button_label}"') \
                    .tooltip(config.link_button_label)

    async def unlink() -> None:
        # In place: the row re-renders under the same document, so ui.notify is
        # correct here and stash_notice would be wrong.
        try:
            await service.unlink_player(user, actor=user)
            ui.notify(config.unlinked_message, color='positive')
        except ValueError as e:
            ui.notify(str(e), color='warning')
        row.refresh()

    async def confirm_unlink() -> None:
        if not config.unlink_confirmation:
            await unlink()
            return

        async def go() -> None:
            dialog.dialog.close()
            await unlink()

        dialog = ConfirmationDialog(
            message=config.unlink_confirmation,
            on_confirm=go,
            confirm_text='Unlink',
            title=f'Unlink {config.title}?',
        )
        dialog.open()

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

    # Where a custom-domain user has to go to link, when the handoff is off and
    # the button cannot work here. Built by the same helper the link route uses
    # for its own detour, rather than reassembling a host in the view; ``None``
    # in path mode, where the rows work in place and this is never read.
    main_site_url = await platform_link_redirect('/home/profile')

    with ui.card().classes('card-full-width'):
        ui.label('Connected accounts').classes('section-title')
        ui.label(
            'Link external accounts to verify your identity and let us find your '
            'bracket and race matches for scheduling.'
        ).classes('text-muted text-caption')
        for i, config in enumerate(active):
            if i:
                ui.separator().classes('q-my-sm')
            _render_provider_row(user, config, main_site_url)
