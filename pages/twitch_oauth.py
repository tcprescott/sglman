"""Twitch OAuth pages.

A single flow: a logged-in user authorizes with Twitch so we can record their
verified Twitch identity (id / login / display name). The token is used once and
discarded.

The CSRF ``state`` + JS-read-callback structure mirrors ``pages/auth.py`` and
``pages/racetime_oauth.py`` — the shared scaffolding lives in
``pages/_oauth_link.py``. When ``MOCK_TWITCH`` is enabled the initiation page
completes the flow locally without contacting Twitch.
"""

from application.services.twitch_service import TwitchService
from application.utils.mock_twitch import is_mock_twitch
from pages._oauth_link import IdentityLinkFlow, register_identity_link_pages

_PROFILE_RETURN = '/home/profile'

_FLOW = IdentityLinkFlow(
    provider_label='Twitch',
    link_route='/twitch/link',
    callback_route='/twitch/oauth/callback',
    state_key='twitch_link_state',
    return_key='twitch_link_return',
    profile_return=_PROFILE_RETURN,
    service_factory=TwitchService,
    authorize_url=TwitchService.player_authorize_url,
    is_mock=is_mock_twitch,
    display_name=lambda me: me.get('display_name') or me.get('username'),
)


def create() -> None:
    register_identity_link_pages(_FLOW)
