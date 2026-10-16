"""The "Use my Discord email" button on Profile → Notifications.

One extra Discord authorization with the ``email`` scope (sign-in keeps asking
for ``identify`` only), run through the shared link scaffolding in
``pages/_oauth_link.py``. Under ``MOCK_DISCORD`` it completes on the spot with a
canned verified address.
"""

from application.services import DiscordEmailService
from application.services.discord.discord_email_service import CALLBACK_PATH
from application.utils.mocks.mock_discord import is_mock_discord
from pages._oauth_link import IdentityLinkFlow, register_identity_link_pages

LINK_ROUTE = '/discord/email/link'

_FLOW = IdentityLinkFlow(
    provider_key='discord-email',
    provider_label='Discord email',
    link_route=LINK_ROUTE,
    callback_route=CALLBACK_PATH,
    state_key='discord_email_state',
    return_key='discord_email_return',
    profile_return='/home/profile?focus=notifications',
    service_factory=DiscordEmailService,
    authorize_url=DiscordEmailService.player_authorize_url,
    is_mock=is_mock_discord,
    display_name=lambda me: me.get('email'),
)


def create() -> None:
    register_identity_link_pages(_FLOW)
