"""Where each notification's call to action goes.

Every DM that asks the recipient to *do* something gets a :class:`DMLink` from
here, which ``send_dm`` renders as a Discord link button and hands to the
web-push mirror as its tap target. One module rather than a private
``_url`` helper per service, because the same three mistakes kept recurring:

* a **relative** path, meaningless in a DM read outside any request context;
* a link to a page that merely *mentions* the thing, leaving the reader to find
  it — the ask has to land on the control that performs it;
* a link to a surface the recipient cannot act on. The matchup-ready DM pointed
  entrants at ``/brackets/<id>``, whose Schedule button is ``is_staff``-gated, so
  the one message in the app whose whole purpose is "go book this" ended at a
  dialog with a Close button. :func:`player_schedule` is that fix.

Every builder returns ``None`` when the tenant cannot be resolved. A DM without a
button is worse than no DM; a DM with a button pointing nowhere is worse than
both, and Discord rejects an empty link URL outright.

Service-layer, not ``utils``: resolving the tenant in scope needs
:class:`TenantService`. The *paths* stay pure in
:mod:`application.utils.app_links`, shared with the pages that render the same
routes.
"""

import logging
from typing import Any, Optional

from application.tenant_context import get_current_tenant_id
from application.utils.app_links import (
    HOME_PLAYER,
    HOME_SCHEDULE,
    HOME_TOURNAMENTS,
    SCHEDULE,
    USERS,
    VOL_SCHEDULE,
    admin_reschedule_request_url,
    admin_url,
    home_url,
    player_reschedule_url,
    player_schedule_url,
)
from application.utils.discord_messages import DMLink
from application.utils.tenant_urls import tenant_url

logger = logging.getLogger(__name__)


async def _current_tenant() -> Optional[Any]:
    """The tenant in scope, or ``None``.

    Callable from a request handler *and* from inside the ``discord_queue``
    worker, which re-binds the enqueuing request's ``tenant_scope`` around each
    coroutine it awaits.
    """
    from application.services.tenant_service import TenantService

    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        return None
    return await TenantService.get_by_id(tenant_id)


async def link_for(label: str, path: str) -> Optional[DMLink]:
    """``label`` → the tenant-absolute form of ``path``, or ``None``.

    Absolute and tenant-qualified because a DM is read outside any request
    context: a bare ``/home/player`` resolves against nothing, and a path-mode
    community's prefix (or its own domain) is exactly what ``tenant_url`` adds.

    Never raises. Every caller is a best-effort notifier that swallows its own
    Discord failures, so a builder that threw here would take the whole DM down
    with it — recipients would lose the message entirely over a decoration on it.
    """
    try:
        tenant = await _current_tenant()
    except Exception:
        logger.exception('notification link lookup failed for %s', path)
        return None
    return link_for_tenant(tenant, label, path)


def link_for_tenant(tenant: Any, label: str, path: str) -> Optional[DMLink]:
    """:func:`link_for` for a caller that already holds the tenant row.

    The qualifier notifications run off a loaded ``run.tenant`` rather than the
    ambient scope, and re-resolving it would be a query for a row in hand.
    """
    return DMLink(label, tenant_url(tenant, path)) if tenant else None


# ---------------------------------------------------------------------------
# Player-facing targets
# ---------------------------------------------------------------------------

async def player_schedule(
    bracket_match_id: int, *, label: str = 'Pick a time',
) -> Optional[DMLink]:
    """"Pick a time" — the Player tab with this matchup's schedule dialog open.

    The entrant's only route to booking a bracket game, and now one press from
    the DM that tells them to book it.
    """
    return await link_for(label, player_schedule_url(bracket_match_id))


async def player_reschedule(
    match_id: int, *, label: str = 'Ask again',
) -> Optional[DMLink]:
    """"Ask again" — the Player tab with this match's request form open.

    A decline is only a dead end if the DM makes it one. The requester's next
    move is a different time, so the button opens the form that takes one.
    """
    return await link_for(label, player_reschedule_url(match_id))


async def player_matches() -> Optional[DMLink]:
    """"View your matches" — the Player tab, the reader's own schedule."""
    return await link_for('View your matches', home_url(HOME_PLAYER))


async def community_schedule(*, label: str = 'View the schedule') -> Optional[DMLink]:
    """The community schedule — for a DM about somebody *else's* match.

    Distinct from :func:`player_matches` because the two read differently: a
    subscriber weighing whether to crew a stream candidate is not being shown
    their own fixture, and a button that says "your matches" would claim they
    were.
    """
    return await link_for(label, home_url(HOME_SCHEDULE))


async def home_tournaments(*, label: str = 'View tournaments') -> Optional[DMLink]:
    """The Tournaments tab — where signing up and withdrawing both happen.

    The signup confirmation's button, so the next thought after "am I in?" —
    checking, or backing out while the window is still open — is one press away
    rather than a hunt through Home.
    """
    return await link_for(label, home_url(HOME_TOURNAMENTS))


async def community_home() -> Optional[DMLink]:
    """"Open the community" — the tenant home, for someone just admitted to it."""
    return await link_for('Open the community', home_url())


# ---------------------------------------------------------------------------
# Staff-facing targets
# ---------------------------------------------------------------------------

async def admin_match(match_id: int, *, label: str = 'Open the match') -> Optional[DMLink]:
    """The admin Schedule board filtered to one match — where crew gets refilled."""
    return await link_for(label, admin_url(SCHEDULE, match_id=match_id))


async def admin_reschedule_request(
    request_id: int, *, label: str = 'Review the request',
) -> Optional[DMLink]:
    """The decision dialog for one reschedule request, open on arrival.

    ``admin_match`` would land staff on the board filtered to the match, which
    shows the schedule but not the ask: the proposed time and the player's
    reason are the whole point and live in the dialog.
    """
    return await link_for(label, admin_reschedule_request_url(request_id))


async def admin_volunteer_schedule(
    day: Any = None, *, label: str = 'Open the shift',
) -> Optional[DMLink]:
    """The volunteer schedule, on the day of the shift that just opened up."""
    return await link_for(label, admin_url(VOL_SCHEDULE, day=day))


async def admin_users(*, label: str = 'Review the request') -> Optional[DMLink]:
    """The Users tab, where join requests are approved or denied."""
    return await link_for(label, admin_url(USERS))
