"""MatchComment reads never cross communities, counts included."""

from application.repositories import MatchCommentRepository
from application.tenant_context import tenant_scope
from models import Match, MatchComment, MatchCommentKind, Tournament
from tests.factories import make_user


async def test_match_comments_are_isolated(two_tenants):
    a, b = two_tenants
    author = await make_user(discord_id=7001, username='author')
    ids = {}
    for tenant in (a, b):
        with tenant_scope(tenant.id):
            t = await Tournament.create(name=f'{tenant.slug} Cup', tenant=tenant)
            m = await Match.create(tournament=t, tenant=tenant)
            c = await MatchComment.create(
                match=m, author=author, kind=MatchCommentKind.PLAYER, body='hi', tenant=tenant,
            )
            ids[tenant.id] = (m.id, c.id)

    (ma, ca), (mb, cb) = ids[a.id], ids[b.id]
    with tenant_scope(a.id):
        assert await MatchCommentRepository.list_for_match(mb) == []
        assert await MatchCommentRepository.counts_by_match([ma, mb]) == {ma: {'player': 1}}
        assert await MatchCommentRepository().get_by_id(cb) is None
    with tenant_scope(b.id):
        assert [c.id for c in await MatchCommentRepository.list_for_match(mb)] == [cb]
        assert await MatchCommentRepository().get_by_id(ca) is None
