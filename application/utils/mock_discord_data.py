"""Fixture data for :class:`MockDiscordService` (development / test only).

This is the single place to define what the fake Discord API "knows about" —
servers (guilds), their roles, per-member role assignments, and who may manage
each server. ``MockDiscordService`` reads everything from here so its methods
stay consistent with one another (a role id returned by ``list_guild_roles`` is
the same id ``get_member_role_ids`` may hand back, etc.).

**Kept in sync with ``scripts/seed_dev.py``:** the two guild ids and the four
*mapped* role ids/names match the dev seed's ``TENANT_SPECS`` and
``role_mapping_specs``, so in ``MOCK_DISCORD`` mode a user's mock Discord roles
actually resolve against the seeded ``DiscordRoleMapping`` rows and login role
sync grants the expected app roles. Extra, unmapped roles are included so the
"Add mapping" UI has a realistic set of choices to pick from.

To enrich the mock: add guilds to :data:`MOCK_GUILDS`, add roles to a guild's
``roles`` list, or pin a specific user's roles in :data:`MOCK_MEMBER_ROLES`.
"""

from typing import Dict, List, Set

# --- Guild ids (match seed_dev.TENANT_SPECS) --------------------------------
GUILD_SGL_DEFAULT = 1000000000000000001
GUILD_SECOND = 1000000000000000002
DEFAULT_GUILD_ID = GUILD_SGL_DEFAULT

# --- Role ids ---------------------------------------------------------------
# Mapped to app roles by seed_dev.role_mapping_specs — keep these ids/names.
ROLE_STAFF = 2000000000000000001
ROLE_PROCTOR = 2000000000000000002
ROLE_STREAM_MANAGER = 2000000000000000003
ROLE_VOLUNTEER = 2000000000000000004
# Unmapped extras — present in the server, available to map in the UI.
ROLE_ADMIN = 2000000000000000010
ROLE_COMMENTATOR = 2000000000000000011
ROLE_TRACKER = 2000000000000000012
ROLE_RESTREAMER = 2000000000000000013

_STANDARD_ROLES: List[Dict[str, object]] = [
    {"id": ROLE_ADMIN, "name": "Admin"},
    {"id": ROLE_STAFF, "name": "SGL Staff"},
    {"id": ROLE_PROCTOR, "name": "Proctors"},
    {"id": ROLE_STREAM_MANAGER, "name": "Stream Managers"},
    {"id": ROLE_VOLUNTEER, "name": "Volunteers"},
    {"id": ROLE_COMMENTATOR, "name": "Commentators"},
    {"id": ROLE_TRACKER, "name": "Trackers"},
    {"id": ROLE_RESTREAMER, "name": "Restreamers"},
]

# owner_id 1 matches the dev seed's first user; member_can_manage_guild treats
# the owner (and Admin/Manage-Server holders) as able to manage the server.
MOCK_GUILDS: Dict[int, dict] = {
    GUILD_SGL_DEFAULT: {
        "name": "SGL Default",
        "owner_id": 1,
        "roles": [dict(r) for r in _STANDARD_ROLES],
    },
    GUILD_SECOND: {
        "name": "Second Community",
        "owner_id": 1,
        "roles": [dict(r) for r in _STANDARD_ROLES],
    },
}

# Pin specific users' roles here (keyed by Discord user id) to script precise
# scenarios. Anyone not listed falls back to :func:`_default_member_roles`.
MOCK_MEMBER_ROLES: Dict[int, Set[int]] = {}


def guild(guild_id: int) -> dict:
    """The guild record for ``guild_id``, or the default guild if unknown.

    Never dead-ends: a fresh dev DB may link a tenant to some other id, and the
    mock should still return a plausible server rather than an error.
    """
    return MOCK_GUILDS.get(guild_id) or MOCK_GUILDS[DEFAULT_GUILD_ID]


def all_guilds() -> List[Dict[str, object]]:
    return [{"id": gid, "name": g["name"]} for gid, g in MOCK_GUILDS.items()]


def roles_for(guild_id: int) -> List[Dict[str, object]]:
    return [dict(r) for r in guild(guild_id)["roles"]]


def _default_member_roles(guild_id: int, user_id: int) -> Set[int]:
    """A deterministic, varied role set so mock role sync does real work.

    Everyone is a Volunteer; higher roles are handed out by simple arithmetic on
    the user id so different impersonated users exercise different mappings.
    """
    granted: Set[int] = {ROLE_VOLUNTEER}
    if user_id % 2 == 0:
        granted.add(ROLE_PROCTOR)
    if user_id % 3 == 0:
        granted.add(ROLE_STAFF)
    if user_id % 5 == 0:
        granted.add(ROLE_STREAM_MANAGER)
    valid = {r["id"] for r in roles_for(guild_id)}
    return granted & valid


def member_role_ids(guild_id: int, user_id: int) -> Set[int]:
    if user_id in MOCK_MEMBER_ROLES:
        return set(MOCK_MEMBER_ROLES[user_id]) & {r["id"] for r in roles_for(guild_id)}
    return _default_member_roles(guild_id, user_id)


def user_can_manage(guild_id: int, user_id: int) -> bool:
    """Owners manage their server; everyone else does in the mock (dev convenience).

    Kept permissive so an impersonated dev user can always exercise the connect
    flow. Pin a scenario by overriding this in a test if you need a denial.
    """
    return True
