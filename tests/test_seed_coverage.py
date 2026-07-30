"""The dev seed's standard, enforced.

``scripts/seed_dev.py`` is the fixture set the /ui-validation browser loop and
every dev environment run against — a model the seed never creates is a feature
no one can see in the running app (CLAUDE.md, "Adding a new feature" step 6).
This runs the real seed against the test harness's in-memory DB and asserts the
rules written down in [docs/reference/dev-seed.md](../docs/reference/dev-seed.md):

* every tenant-scoped model has a row, and re-seeding never duplicates one;
* every value of every enum stored on a model appears somewhere, or is exempted
  here with a reason;
* fixture discord ids are derived and unique — a collision once renamed another
  fixture out of existence;
* every per-tenant role has a holder who holds *only* that role;
* the fixtures defined by an absence still have one.
"""

from tortoise.models import Model

import models as _models
from models import Role, TenantMembership, User, UserRole
from scripts.seed_support import ALL_FIXTURE_USERNAMES, fixture_discord_id
from tests.conftest import DEFAULT_TEST_TENANT_ID, _scoped_models

# Model name -> one-line reason a runtime-artifact model is excused from the
# seed. Keep empty unless a model genuinely cannot be seeded.
EXEMPT: dict[str, str] = {}

# "Model.field" -> reason that field is excused from full enum coverage. An entry
# here is a claim that seeding the missing values would be *wrong*, not merely
# inconvenient — keep it that way.
ENUM_EXEMPT: dict[str, str] = {
    'DiscordRoleMapping.app_role': (
        'A community maps the roles its own guild happens to have, so a mapping '
        'per Role would describe no real guild — and SUPER_ADMIN is global and '
        'not grantable per tenant, so mapping it would be a bug. UserRole.role '
        'is where every Role is covered.'
    ),
}

#: Holds no per-tenant role by design, so it cannot be a single-capability
#: holder: SUPER_ADMIN's UserRole row carries ``tenant=NULL``.
_GLOBAL_ROLES = {Role.SUPER_ADMIN}


def _enum_fields() -> list[tuple[type[Model], str, type]]:
    """Every (model, field, enum) triple stored as an enum column."""
    found = []
    for obj in vars(_models).values():
        if not (isinstance(obj, type) and issubclass(obj, Model) and obj is not Model):
            continue
        for name, field in obj._meta.fields_map.items():
            enum_type = getattr(field, 'enum_type', None)
            if enum_type is not None and hasattr(enum_type, '__members__'):
                found.append((obj, name, enum_type))
    return found


async def test_seed_covers_every_tenant_scoped_model(db):
    from scripts.seed_dev import seed_all

    await seed_all()

    missing = [
        m.__name__
        for m in _scoped_models()
        if m.__name__ not in EXEMPT
        and not await m.filter(tenant_id=DEFAULT_TEST_TENANT_ID).exists()
    ]
    assert not missing, (
        f"scripts/seed_dev.py leaves these tenant-FK models empty for the "
        f"default tenant: {missing}. Add at least one representative row per "
        f"meaningful state (add-feature skill, step 6), or record a reason in "
        f"EXEMPT above."
    )


async def test_seed_is_idempotent_for_scoped_models(db):
    from scripts.seed_dev import seed_all

    await seed_all()
    counts = {
        m.__name__: await m.filter(tenant_id=DEFAULT_TEST_TENANT_ID).count()
        for m in _scoped_models()
    }
    await seed_all()
    recounts = {
        m.__name__: await m.filter(tenant_id=DEFAULT_TEST_TENANT_ID).count()
        for m in _scoped_models()
    }
    grew = {n: (counts[n], recounts[n]) for n in counts if recounts[n] != counts[n]}
    assert not grew, f"re-running seed_all() duplicated rows: {grew}"


async def test_seed_covers_every_enum_value(db):
    """A state the seed never creates is a state nobody can re-check.

    Enum values are the states the schema itself names, so they are the one set
    of states that can be checked mechanically — which is why the bar is drawn
    here rather than at "states we happened to think of".
    """
    from scripts.seed_dev import seed_all

    await seed_all()

    gaps: dict[str, list[str]] = {}
    for model, field, enum_type in _enum_fields():
        key = f'{model.__name__}.{field}'
        if key in ENUM_EXEMPT:
            continue
        stored = set(await model.all().distinct().values_list(field, flat=True))
        stored = {getattr(value, 'value', value) for value in stored}
        missing = [member.value for member in enum_type if member.value not in stored]
        if missing:
            gaps[key] = missing

    assert not gaps, (
        f"the dev seed never produces these enum values: {gaps}. Seed a row in "
        f"each state (docs/reference/dev-seed.md), or record in ENUM_EXEMPT "
        f"above why seeding it would misrepresent the app."
    )


def test_fixture_discord_ids_are_unique():
    """Derived ids must not collide.

    ``cc_user`` and ``outsider`` once shared a hand-written id, so the seed
    created the outsider fixture and then renamed it — taking the membership
    gate's only fixture with it, silently. Ids are derived now; this is what
    makes "derived" safe.
    """
    ids: dict[str, str] = {}
    for username in ALL_FIXTURE_USERNAMES:
        discord_id = fixture_discord_id(username)
        assert discord_id not in ids, (
            f"fixture discord id collision: '{username}' and '{ids[discord_id]}' "
            f"both derive {discord_id}. Rename one of them."
        )
        ids[discord_id] = username


def test_every_fixture_username_is_unique():
    """The username is the key the whole seed (and the id derivation) turns on."""
    duplicates = {
        name for name in ALL_FIXTURE_USERNAMES
        if ALL_FIXTURE_USERNAMES.count(name) > 1
    }
    assert not duplicates, f"duplicate fixture usernames: {sorted(duplicates)}"


async def test_every_per_tenant_role_has_a_single_capability_holder(db):
    """Each role needs a holder who holds *nothing else*.

    ``staff_user`` satisfies every predicate in the admin area, so a surface that
    gates on staff-ness where it means to gate on a capability looks correct in
    dev until the delegate it was written for logs in. A role whose only holders
    also hold something else cannot catch that.
    """
    from scripts.seed_dev import seed_all

    await seed_all()

    held: dict[int, set[Role]] = {}
    for grant in await UserRole.filter(tenant_id=DEFAULT_TEST_TENANT_ID):
        held.setdefault(grant.user_id, set()).add(Role(grant.role))
    sole = {roles.pop() for roles in (set(r) for r in held.values()) if len(roles) == 1}

    missing = sorted(
        role.value for role in Role
        if role not in _GLOBAL_ROLES and role not in sole
    )
    assert not missing, (
        f"no seeded user holds these roles and nothing else: {missing}. Add a "
        f"holder to USER_SPECS in scripts/seed_support.py and grant it in "
        f"seed_dev.seed_for_tenant (docs/reference/dev-seed.md)."
    )


async def test_the_outsider_fixture_belongs_to_no_community(db):
    """The fixture defined by an absence still has to have one.

    ``outsider`` is what makes the membership gate's join page reachable in dev.
    It has been quietly deleted once already, by an id collision, and nothing
    failed.
    """
    from scripts.seed_dev import seed_all

    await seed_all()

    outsider = await User.get_or_none(discord_id=fixture_discord_id('outsider'))
    assert outsider is not None, "the 'outsider' fixture is missing entirely"
    assert outsider.username == 'outsider', (
        f"the derived id for 'outsider' is held by '{outsider.username}' — a "
        f"collision has renamed the fixture"
    )
    memberships = await TenantMembership.filter(user=outsider).count()
    assert memberships == 0, (
        f"'outsider' belongs to {memberships} communities; the join page is only "
        f"reachable in dev as a user who belongs to none"
    )
