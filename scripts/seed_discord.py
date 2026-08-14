"""Dev-seed fixtures for one tenant's Discord role mappings.

Split out of ``seed_dev.py`` when that module crossed the 800-line budget again,
following the ``seed_equipment_for_tenant`` / ``seed_volunteers_for_tenant``
convention already used there: one module per domain, called from inside the
caller's ``tenant_scope``. Idempotent and tenant-stamped like every other seeded
row.

Each tenant maps its own guild's roles, and the fixtures cover both shapes the
table holds — a guild role onto a community-wide app role, and a guild role onto
one tournament's grants — because the admin tab renders them side by side. The
``DiscordTournamentGrant`` rows are the provenance sync would leave behind, so
the "a re-sync may take this back" state sits next to a hand-made grant that it
may not.
"""

from models import (
    DiscordRoleMapping,
    DiscordTournamentGrant,
    Role,
    Tenant,
    Tournament,
    TournamentGrant,
    User,
)


async def seed_discord_for_tenant(
    tenant: Tenant, tournament: Tournament, users: dict[str, User]
) -> None:
    """Seed one tenant's guild-role mappings and the grants sync would produce."""
    # Each tenant maps its own guild's roles onto app roles.
    guild_id = tenant.discord_guild_id
    role_mapping_specs = [
        (2000000000000000001, "Wizzrobe Staff", Role.STAFF),
        (2000000000000000002, "Proctors", Role.PROCTOR),
        (2000000000000000003, "Stream Managers", Role.STREAM_MANAGER),
        (2000000000000000004, "Volunteers", Role.VOLUNTEER),
    ]
    for discord_role_id, discord_role_name, app_role in role_mapping_specs:
        await DiscordRoleMapping.get_or_create(
            guild_id=guild_id, discord_role_id=discord_role_id, app_role=app_role,
            tenant=tenant, defaults={"discord_role_name": discord_role_name},
        )
    # The other shape of mapping: a guild role onto one tournament's grants
    # rather than a community-wide role. Both live in the same table and the
    # admin tab renders them side by side, so the seed needs one of each.
    for discord_role_id, discord_role_name, grant in [
        (2000000000000000005, "Event Admins", TournamentGrant.TOURNAMENT_ADMIN),
        (2000000000000000006, "Crew Leads", TournamentGrant.CREW_COORDINATOR),
    ]:
        await DiscordRoleMapping.get_or_create(
            guild_id=guild_id, discord_role_id=discord_role_id,
            tournament_grant=grant, tournament=tournament, tenant=tenant,
            defaults={"discord_role_name": discord_role_name},
        )
    # And the provenance rows sync would leave behind, so the "a re-sync may
    # take this back" state sits next to a hand-made grant that it may not:
    # staff holds both grants manually, these two came from the guild roles.
    for uname, grant in [
        ("player_three", TournamentGrant.CREW_COORDINATOR),
        ("player_four", TournamentGrant.TOURNAMENT_ADMIN),
    ]:
        relation = (
            tournament.admins if grant == TournamentGrant.TOURNAMENT_ADMIN
            else tournament.crew_coordinators
        )
        await relation.add(users[uname])
        await DiscordTournamentGrant.get_or_create(
            tournament=tournament, user=users[uname], grant=grant,
            defaults={"tenant": tenant},
        )
    print(f"    [{tenant.slug}] discord role mappings ok")
