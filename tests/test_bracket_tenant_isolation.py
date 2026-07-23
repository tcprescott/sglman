"""Cross-tenant isolation (leak) tests for the native bracket models.

All four models — Bracket, BracketEntrant, BracketEntry, BracketMatch — carry a
``tenant`` FK, so a tenant-scoped read must return only that tenant's rows. B0
has no repository yet (that arrives in B6); these tests exercise the same
``scoped()`` helper the repositories will use, which is what enforces the
contract in production.
"""

from application.repositories._tenant import scoped
from application.tenant_context import tenant_scope
from models import (
    Bracket,
    BracketEntrant,
    BracketEntry,
    BracketFormat,
    BracketMatch,
    Tournament,
    User,
)


async def _tournament(name: str) -> Tournament:
    # tenant is auto-stamped from the ambient scope by the test db fixture.
    return await Tournament.create(name=name)


async def test_bracket_reads_are_isolated(two_tenants):
    a, b = two_tenants
    with tenant_scope(a.id):
        ta = await _tournament('TA')
        ba = await Bracket.create(tournament=ta, name='Main', format=BracketFormat.SINGLE_ELIM)
    with tenant_scope(b.id):
        tb = await _tournament('TB')
        bb = await Bracket.create(tournament=tb, name='Main', format=BracketFormat.SINGLE_ELIM)

    with tenant_scope(a.id):
        assert [x.id for x in await scoped(Bracket.all())] == [ba.id]
        assert await scoped(Bracket.filter(id=bb.id)).first() is None
    with tenant_scope(b.id):
        assert [x.id for x in await scoped(Bracket.all())] == [bb.id]
        assert await scoped(Bracket.filter(id=ba.id)).first() is None


async def test_bracket_entrant_reads_are_isolated(two_tenants):
    a, b = two_tenants
    with tenant_scope(a.id):
        ta = await _tournament('TA')
        ea = await BracketEntrant.create(tournament=ta, display_name='Alice')
    with tenant_scope(b.id):
        tb = await _tournament('TB')
        eb = await BracketEntrant.create(tournament=tb, display_name='Alice')  # same name, other tenant

    with tenant_scope(a.id):
        assert [x.id for x in await scoped(BracketEntrant.all())] == [ea.id]
        assert await scoped(BracketEntrant.filter(id=eb.id)).first() is None
    with tenant_scope(b.id):
        assert [x.id for x in await scoped(BracketEntrant.all())] == [eb.id]
        assert await scoped(BracketEntrant.filter(id=ea.id)).first() is None


async def test_bracket_entry_reads_are_isolated(two_tenants):
    a, b = two_tenants
    with tenant_scope(a.id):
        ta = await _tournament('TA')
        ba = await Bracket.create(tournament=ta, name='Main', format=BracketFormat.SWISS)
        enta = await BracketEntrant.create(tournament=ta, display_name='Alice')
        rowa = await BracketEntry.create(bracket=ba, entrant=enta, seed=1)
    with tenant_scope(b.id):
        tb = await _tournament('TB')
        bb = await Bracket.create(tournament=tb, name='Main', format=BracketFormat.SWISS)
        entb = await BracketEntrant.create(tournament=tb, display_name='Bob')
        rowb = await BracketEntry.create(bracket=bb, entrant=entb, seed=1)

    with tenant_scope(a.id):
        assert [x.id for x in await scoped(BracketEntry.all())] == [rowa.id]
        assert await scoped(BracketEntry.filter(id=rowb.id)).first() is None
    with tenant_scope(b.id):
        assert [x.id for x in await scoped(BracketEntry.all())] == [rowb.id]
        assert await scoped(BracketEntry.filter(id=rowa.id)).first() is None


async def test_bracket_match_reads_are_isolated(two_tenants):
    a, b = two_tenants
    with tenant_scope(a.id):
        ta = await _tournament('TA')
        ba = await Bracket.create(tournament=ta, name='Main', format=BracketFormat.DOUBLE_ELIM)
        ma = await BracketMatch.create(bracket=ba, round=1, position=1)
    with tenant_scope(b.id):
        tb = await _tournament('TB')
        bb = await Bracket.create(tournament=tb, name='Main', format=BracketFormat.DOUBLE_ELIM)
        mb = await BracketMatch.create(bracket=bb, round=1, position=1)

    with tenant_scope(a.id):
        assert [x.id for x in await scoped(BracketMatch.all())] == [ma.id]
        assert await scoped(BracketMatch.filter(id=mb.id)).first() is None
    with tenant_scope(b.id):
        assert [x.id for x in await scoped(BracketMatch.all())] == [mb.id]
        assert await scoped(BracketMatch.filter(id=ma.id)).first() is None
