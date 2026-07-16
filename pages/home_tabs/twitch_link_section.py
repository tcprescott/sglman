"""Self-contained 'Link Twitch' section for the player profile tab.

Lets a user verify-link their Twitch identity via a one-time OAuth login. The
section hides itself entirely when the Twitch integration isn't configured.
"""

from application.services import TwitchService
from models import User
from pages.home_tabs._link_section import LinkSectionConfig, render_link_section

_CONFIG = LinkSectionConfig(
    title='Twitch',
    description=(
        'Link your Twitch account so we can associate your verified Twitch identity '
        'with your profile.'
    ),
    link_route='/twitch/link',
    link_button_label='Link Twitch account',
    unlinked_message='Twitch account unlinked.',
    user_id_attr='twitch_user_id',
    username_attr='twitch_username',
    service_factory=TwitchService,
)


async def render_twitch_link_section(user: User) -> None:
    await render_link_section(user, _CONFIG)
