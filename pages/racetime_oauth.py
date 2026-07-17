"""racetime.gg OAuth pages.

A single flow: a logged-in user authorizes with racetime.gg (read scope) so we
can record their verified racetime identity (id / name). The token is used once
and discarded.

The CSRF ``state`` + JS-read-callback structure mirrors ``pages/auth.py`` and
``pages/twitch_oauth.py`` — the shared scaffolding lives in
``pages/_oauth_link.py``. When ``MOCK_RACETIME`` is enabled the initiation page
completes the flow locally without contacting racetime.gg.
"""

from application.services.racetime_service import RacetimeService
from application.utils.mock_racetime import is_mock_racetime
from pages._oauth_link import IdentityLinkFlow, register_identity_link_pages

_PROFILE_RETURN = '/home/profile'

_FLOW = IdentityLinkFlow(
    provider_label='racetime',
    link_route='/racetime/link',
    callback_route='/racetime/oauth/callback',
    state_key='racetime_link_state',
    return_key='racetime_link_return',
    profile_return=_PROFILE_RETURN,
    service_factory=RacetimeService,
    authorize_url=RacetimeService.player_authorize_url,
    is_mock=is_mock_racetime,
    display_name=lambda me: me.get('username'),
)


def create() -> None:
    register_identity_link_pages(_FLOW)
