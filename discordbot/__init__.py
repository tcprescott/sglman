"""Discord bot package.

Importing this package wires the bot's component-interaction handlers and DM
view factories into ``application.services.discord_service`` via its registries.

This is the inversion of what used to be a bidirectional import cycle between
``discord_service.py`` and ``discordbot/`` — previously held together only by
~20 deferred, function-body imports on both sides. The dependency now runs one
way (``discordbot`` -> ``application.services``); ``discord_service`` no longer
imports ``discordbot`` at all. Mirrors ``application/match_events.py``. See
docs/reviews/2026-07-project-structure-review.md, roadmap item 21.

``main.py``'s lifespan imports this package once at startup so the registration
runs before any Discord interaction is dispatched or DM is sent.
"""

from application.services.discord_service import (
    VIEW_CREW_ACK,
    VIEW_CREW_SIGNUP,
    VIEW_MATCH_ACK,
    VIEW_UNWATCH,
    VIEW_VOLUNTEER_ACK,
    register_interaction_handler,
    register_view_factory,
)
from discordbot.crew_acknowledgment import (
    CUSTOM_ID_PREFIX as CREW_ACK_PREFIX,
    handle_crew_acknowledgment_interaction,
    make_crew_acknowledgment_view,
)
from discordbot.crew_signup import (
    CUSTOM_ID_PREFIX as CREW_SIGNUP_PREFIX,
    handle_crew_signup_interaction,
    make_crew_signup_view,
)
from discordbot.match_acknowledgment import (
    CUSTOM_ID_PREFIX as MATCH_ACK_PREFIX,
    handle_match_acknowledgment_interaction,
    make_match_acknowledgment_view,
)
from discordbot.volunteer_acknowledgment import (
    CUSTOM_ID_PREFIX as VOLUNTEER_ACK_PREFIX,
    handle_volunteer_acknowledgment_interaction,
    make_volunteer_acknowledgment_view,
)
from discordbot.watch_buttons import (
    CUSTOM_ID_PREFIX as WATCH_PREFIX,
    handle_unwatch_interaction,
    make_unwatch_view,
)

# Component-interaction handlers, keyed by the custom_id prefix baked into each
# button (text before the first ':').
register_interaction_handler(CREW_SIGNUP_PREFIX, handle_crew_signup_interaction)
register_interaction_handler(MATCH_ACK_PREFIX, handle_match_acknowledgment_interaction)
register_interaction_handler(CREW_ACK_PREFIX, handle_crew_acknowledgment_interaction)
register_interaction_handler(VOLUNTEER_ACK_PREFIX, handle_volunteer_acknowledgment_interaction)
register_interaction_handler(WATCH_PREFIX, handle_unwatch_interaction)

# DM view factories, keyed by the VIEW_* kinds the DM senders look up.
register_view_factory(VIEW_CREW_SIGNUP, make_crew_signup_view)
register_view_factory(VIEW_MATCH_ACK, make_match_acknowledgment_view)
register_view_factory(VIEW_CREW_ACK, make_crew_acknowledgment_view)
register_view_factory(VIEW_VOLUNTEER_ACK, make_volunteer_acknowledgment_view)
register_view_factory(VIEW_UNWATCH, make_unwatch_view)
