"""Scope catalogue for third-party app grants.

Pure metadata, a peer of :mod:`application.feature_flags`: import-safe from
every layer. The stable keys live in :class:`models.enums.OAuthScope`; the
consent wording and the groupings that decide what a grant may do live here, so
the authorization server, the consent screen and the REST scope check read one
source.

A scope only ever narrows. What a grant can do is what its scopes cover AND
what the person's own roles in that community allow, so losing a role takes
effect at once without re-consent.
"""

from typing import Dict, FrozenSet, Iterable, List, Set

from models import OAuthScope

#: Shown on the consent screen, one line per scope.
SCOPE_DESCRIPTIONS: Dict[OAuthScope, str] = {
    OAuthScope.PROFILE: 'See your Wizzrobe profile and availability',
    OAuthScope.PROFILE_WRITE: 'Update your availability and notification settings',
    OAuthScope.SCHEDULE_READ: 'See tournaments, matches, brackets and the schedule',
    OAuthScope.PLAY: 'Act as you as a player',
    OAuthScope.CREW: 'Sign you up or withdraw you as crew',
    OAuthScope.VOLUNTEER: 'See and manage your volunteer shifts',
    OAuthScope.STAFF_READ: (
        'See staff-only information (reports, audit log, member list, '
        'equipment, check-in)'
    ),
    OAuthScope.STAFF_WRITE: 'Make staff changes in this community',
}

#: Scopes that let a grant change something. A grant holding none of these is
#: stamped ``read_only``, which every write route already refuses.
WRITE_SCOPES: FrozenSet[OAuthScope] = frozenset({
    OAuthScope.PROFILE_WRITE,
    OAuthScope.PLAY,
    OAuthScope.CREW,
    OAuthScope.VOLUNTEER,
    OAuthScope.STAFF_WRITE,
})

#: Offered on consent only to someone who holds a role that could use them in
#: the picked community; dropped silently for everyone else.
STAFF_SCOPES: FrozenSet[OAuthScope] = frozenset({OAuthScope.STAFF_READ, OAuthScope.STAFF_WRITE})

ALL_SCOPES: List[OAuthScope] = list(OAuthScope)


def parse_scope(value: str | Iterable[str] | None) -> Set[OAuthScope]:
    """A space-separated scope string (or list of names) as a set.

    Raises ``ValueError`` naming the first unknown scope, so a typo in an app's
    request is reported rather than silently dropped.
    """
    if value is None:
        return set()
    names = value.split() if isinstance(value, str) else list(value)
    scopes: Set[OAuthScope] = set()
    for name in names:
        try:
            scopes.add(OAuthScope(name))
        except ValueError:
            raise ValueError(f'Unknown scope: {name}') from None
    return scopes


def format_scope(scopes: Iterable[OAuthScope]) -> str:
    """Space-separated, in catalogue order, so equal sets give equal strings."""
    wanted = set(scopes)
    return ' '.join(s.value for s in ALL_SCOPES if s in wanted)


def grants_write(scopes: Iterable[OAuthScope]) -> bool:
    return any(s in WRITE_SCOPES for s in scopes)
