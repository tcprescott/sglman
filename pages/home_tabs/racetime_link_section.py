"""Self-contained 'Link racetime.gg' section for the player profile tab.

Lets a user verify-link their racetime.gg identity via a one-time OAuth login.
The section hides itself entirely when the racetime integration isn't configured.
"""

from application.services import RacetimeService
from models import User
from pages.home_tabs._link_section import LinkSectionConfig, render_link_section

_CONFIG = LinkSectionConfig(
    title='racetime.gg',
    description=(
        'Link your racetime.gg account so we can attribute your race results and '
        'check auto-open eligibility.'
    ),
    link_route='/racetime/link',
    link_button_label='Link racetime.gg account',
    unlinked_message='racetime.gg account unlinked.',
    user_id_attr='racetime_user_id',
    username_attr='racetime_username',
    service_factory=RacetimeService,
)


async def render_racetime_link_section(user: User) -> None:
    await render_link_section(user, _CONFIG)
