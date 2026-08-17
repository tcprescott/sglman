"""Row builders the DB-backed MatchService test modules share.

``test_match_service_coverage`` (reads, stream candidate, stage, stations,
delete, results, enrolment) and ``test_match_write_coverage`` (create_match and
update_match) were one module until it approached the 800-line guideline. Both
build the same three rows to get to the thing under test.

``make_player`` is a thin front for ``tests.factories.make_user``: it hands out
a fresh discord id per call — the tests never care which — and grants roles,
which is what the permission gates need. It is deliberately not called
``make_user``; the shared factory owns that name.
"""

import itertools

from models import Role, Tournament, User, UserRole
from tests.factories import make_user

_discord_ids = itertools.count(9000)


async def make_player(username="player", display_name=None, roles=None) -> User:
    user = await make_user(
        discord_id=next(_discord_ids),
        username=username,
        display_name=display_name if display_name is not None else username,
    )
    for role in roles or []:
        await UserRole.create(user=user, role=role)
    return user


async def make_staff(username="staff") -> User:
    return await make_player(username=username, roles=[Role.STAFF])


async def make_tournament(**overrides) -> Tournament:
    fields = dict(name="Test Tournament", players_per_match=2, seed_generator=None)
    fields.update(overrides)
    return await Tournament.create(**fields)
