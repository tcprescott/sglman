"""Which stages a viewer may see — enforced in ``BracketService``, for every surface.

A DRAFT stage is unpublished and a CANCELLED one withdrawn; both are staff-only.
A tournament with nothing published has not been announced, so its name is not
public either. The rule used to be a presentation filter the bracket pages, the
join door and the browse tab each applied — and REST and MCP did not, so any
token holder could list drafts with their config and seeded field. The
viewer-aware reads here are what every surface now calls.
"""

from pathlib import Path

import pytest

from application.services import BracketService
from models import Bracket, BracketFormat, BracketState, Role, Tournament, UserRole
from tests.factories import make_user


async def _staff():
    user = await make_user(discord_id=9001, username='staff')
    await UserRole.create(user=user, role=Role.STAFF)
    return user


async def _stage(tournament, name, state, order=1):
    return await Bracket.create(
        tournament=tournament, name=name, format=BracketFormat.SINGLE_ELIM, state=state,
        stage_order=order,
    )


@pytest.fixture
async def field(db):
    """One announced tournament (a draft, a live and a cancelled stage) and one
    that has only a draft."""
    public = await Tournament.create(name='Spring Cup')
    secret = await Tournament.create(name='Secret Invitational')
    stages = {
        'draft': await _stage(public, 'Draft', BracketState.DRAFT, 1),
        'active': await _stage(public, 'Main', BracketState.ACTIVE, 2),
        'cancelled': await _stage(public, 'Abandoned', BracketState.CANCELLED, 3),
        'secret': await _stage(secret, 'Secret Draft', BracketState.DRAFT),
    }
    return public, secret, stages


class TestPublishedRule:
    @pytest.mark.parametrize('state, published', [
        (BracketState.DRAFT, False),
        (BracketState.CANCELLED, False),
        (BracketState.ACTIVE, True),
        (BracketState.COMPLETE, True),
    ])
    def test_only_started_stages_are_public(self, state, published):
        class _Stage:
            pass

        stage = _Stage()
        stage.state = state
        assert BracketService.is_published(stage) is published


class TestSignedOutAndNonStaff:
    async def test_a_tournaments_list_drops_drafts_and_withdrawn_stages(self, field):
        public, _secret, stages = field
        player = await make_user(discord_id=9002, username='player')
        for viewer in (None, player):
            listed = await BracketService().list_visible_brackets(viewer, public.id)
            assert [b.id for b in listed] == [stages['active'].id]

    async def test_an_unpublished_stage_reads_as_missing(self, field):
        _public, _secret, stages = field
        service = BracketService()
        assert await service.get_visible_bracket(None, stages['draft'].id) is None
        assert await service.get_visible_bracket(None, stages['cancelled'].id) is None
        assert (await service.get_visible_bracket(None, stages['active'].id)).id == stages['active'].id

    async def test_an_unannounced_tournament_does_not_give_its_name_away(self, field):
        public, secret, _stages = field
        service = BracketService()
        assert await service.get_visible_tournament(None, secret.id) is None
        assert (await service.get_visible_tournament(None, public.id)).name == 'Spring Cup'

    async def test_the_browse_list_is_filtered_too(self, field):
        _public, _secret, stages = field
        listed = await BracketService().list_all_visible_brackets(None)
        assert {b.id for b in listed} == {stages['active'].id}


class TestStaff:
    async def test_staff_see_everything(self, field):
        public, secret, stages = field
        staff = await _staff()
        service = BracketService()
        assert len(await service.list_visible_brackets(staff, public.id)) == 3
        assert await service.get_visible_bracket(staff, stages['draft'].id) is not None
        assert (await service.get_visible_tournament(staff, secret.id)).name == 'Secret Invitational'
        assert len(await service.list_all_visible_brackets(staff)) == 4


class TestEverySurfaceAsksTheService:
    """The pages cannot be built without a NiceGUI client, so this pins that the
    public surfaces route through the viewer-aware reads rather than filtering
    an unfiltered list themselves — the shape that let REST and MCP drift."""

    @pytest.mark.parametrize('path, needle', [
        ('pages/brackets.py', 'get_visible_tournament(user, tid)'),
        ('pages/brackets.py', 'list_visible_brackets(user, tid)'),
        ('pages/brackets.py', 'get_visible_bracket(user, parsed_id)'),
        ('pages/static_brackets.py', 'get_visible_tournament(None, tid)'),
        ('pages/static_brackets.py', 'get_visible_bracket(None, stage_id)'),
        ('theme/join_page.py', 'list_all_visible_brackets(None)'),
        ('pages/home_tabs/brackets.py', 'list_all_visible_brackets(user)'),
        ('api/routers/brackets.py', 'list_visible_brackets(actor, tournament_id)'),
        ('mcpserver/tools/competition.py', 'list_visible_brackets(current_actor().user'),
    ])
    def test_surface_uses_the_viewer_aware_read(self, path, needle):
        assert needle in Path(path).read_text()

    @pytest.mark.parametrize('path', [
        'pages/brackets.py', 'pages/static_brackets.py', 'theme/join_page.py',
        'pages/home_tabs/brackets.py', 'mcpserver/tools/competition.py',
    ])
    def test_no_public_surface_reads_the_unfiltered_list(self, path):
        source = Path(path).read_text()
        assert 'list_all_brackets(' not in source
        assert '.get_bracket(' not in source
