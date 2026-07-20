"""Challonge provider config for the profile 'Connected accounts' section.

Lets a player verify-link their Challonge identity (one-time OAuth, scope
``me``) so they can be matched to bracket participants for scheduling. Rendered
(alongside the other providers) by :func:`render_connected_accounts_section`,
which hides any provider whose integration isn't configured.
"""

from application.services import ChallongeService
from pages.home_tabs._link_section import LinkSectionConfig

CONFIG = LinkSectionConfig(
    title='Challonge',
    icon='emoji_events',
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
