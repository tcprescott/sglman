"""Self-contained 'Link Challonge' section for the player profile tab.

Lets a player verify-link their Challonge identity (one-time OAuth, scope
``me``) so they can be matched to bracket participants for scheduling. The
section hides itself entirely when the Challonge integration isn't configured.
"""

from application.services import ChallongeService
from models import User
from pages.home_tabs._link_section import LinkSectionConfig, render_link_section

_CONFIG = LinkSectionConfig(
    title='Challonge',
    description=(
        'Link your Challonge account so we can find your bracket matches and let you '
        'schedule them here.'
    ),
    link_route='/challonge/link',
    link_button_label='Link Challonge account',
    unlinked_message='Challonge account unlinked.',
    user_id_attr='challonge_user_id',
    username_attr='challonge_username',
    service_factory=ChallongeService,
)


async def render_challonge_link_section(user: User) -> None:
    await render_link_section(user, _CONFIG)
