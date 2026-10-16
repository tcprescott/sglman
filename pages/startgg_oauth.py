"""start.gg OAuth pages: a logged-in player links their start.gg account.

Same scaffolding as ``pages/twitch_oauth.py`` (``pages/_oauth_link.py``). The
callback is registered on the platform host; custom-domain communities reach it
through the existing handoff. When ``MOCK_STARTGG`` is on the link page
completes locally.
"""

from application.services.startgg_link_service import StartggLinkService
from application.utils.mocks.mock_startgg import is_mock_startgg
from pages._oauth_link import IdentityLinkFlow, register_identity_link_pages

_FLOW = IdentityLinkFlow(
    provider_key='startgg',
    provider_label='start.gg',
    link_route='/startgg/link',
    callback_route='/startgg/oauth/callback',
    state_key='startgg_link_state',
    return_key='startgg_link_return',
    profile_return='/home/profile',
    service_factory=StartggLinkService,
    authorize_url=StartggLinkService.player_authorize_url,
    is_mock=is_mock_startgg,
    display_name=lambda me: me.get('display_name') or me.get('username'),
)


def create() -> None:
    register_identity_link_pages(_FLOW)
