"""Tests for attaching a manually-scheduled ``Match`` to a bracket matchup.

The staff counterpart of ``schedule_bracket_match``: an admin who scheduled a
match through the ordinary editor can link it to the matchup it settles, and
detach it again while it is still unplayed.

The player-set check gets the most attention here because it is the one whose
failure is silent: ``SeriesMixin._winner_from_ranks`` maps a winner by matching
``MatchPlayers.user_id`` against the two entrants, so a mismatched link would
settle nothing and strand the series with nothing surfaced anywhere.
"""

import pytest

from application.services.bracket_service import BracketService
from models import (
    BracketMatchGame,
    BracketMatchGameState,
    BracketMatchState,
    Match,
    MatchPlayers,
    Role,
    Tournament,
    User,
    UserRole,
)

pytestmark = pytest.mark.usefixtures("db")


async def _staff(discord_id: int = 4100, username: str = 'staff') -> User:
    user = await User.create(discord_id=discord_id, username=username)
    await UserRole.create(user=user, role=Role.STAFF)
    return user


async def _player(discord_id: int, username: str) -> User:
    return await User.create(discord_id=discord_id, username=username)


@pytest.fixture
def service() -> BracketService:
    return BracketService()


async def _bracket(service, actor):
    """A started 2-entrant single-elim bracket with both entrants linked."""
    t = await Tournament.create(name='Cup')
    bracket = await service.create_bracket(actor, t.id, 'Main', 'single_elim')
    users = []
    for i in (1, 2):
        user = await _player(4200 + i, f'p{i}')
        users.append(user)
        entrant = await service.add_entrant(actor, t.id, f'P{i}', user_id=user.id)
        await service.enroll(actor, bracket.id, entrant.id, seed=i)
    await service.start_bracket(actor, bracket.id)
    bmatch = (await service.get_open_matches(bracket.id))[0]
    return t, bracket, users, bmatch


async def _match(tournament, users) -> Match:
    match = await Match.create(tournament=tournament)
    for user in users:
        await MatchPlayers.create(match=match, user=user)
    return match


class TestLinkMatchToBracketMatch:
    async def test_links_and_assigns_the_next_game_number(self, service):
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        match = await _match(t, users)

        game = await service.link_match_to_bracket_match(actor, bmatch.id, match.id)

        assert game.game_number == 1
        assert game.match_id == match.id
        assert game.state == BracketMatchGameState.SCHEDULED
        assert await service.list_linkable_matches(t.id) == []

    async def test_mismatched_players_rejected(self, service):
        """The check that keeps advancement from silently never resolving."""
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        stranger = await _player(4300, 'stranger')
        match = await _match(t, [users[0], stranger])

        with pytest.raises(ValueError, match="players don't match"):
            await service.link_match_to_bracket_match(actor, bmatch.id, match.id)

    async def test_other_tournament_rejected(self, service):
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        other = await Tournament.create(name='Other')
        match = await _match(other, users)

        with pytest.raises(ValueError, match='different tournament'):
            await service.link_match_to_bracket_match(actor, bmatch.id, match.id)

    async def test_already_linked_match_rejected(self, service):
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        match = await _match(t, users)
        await service.link_match_to_bracket_match(actor, bmatch.id, match.id)

        with pytest.raises(ValueError, match='already linked'):
            await service.link_match_to_bracket_match(actor, bmatch.id, match.id)

    async def test_full_series_rejected(self, service):
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        await service.link_match_to_bracket_match(
            actor, bmatch.id, (await _match(t, users)).id,
        )
        second = await _match(t, users)

        with pytest.raises(ValueError, match='already scheduled'):
            await service.link_match_to_bracket_match(actor, bmatch.id, second.id)

    async def test_completed_matchup_rejected(self, service):
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        bmatch.state = BracketMatchState.COMPLETE
        await bmatch.save()
        match = await _match(t, users)

        with pytest.raises(ValueError, match='already decided'):
            await service.link_match_to_bracket_match(actor, bmatch.id, match.id)

    async def test_player_rejected(self, service):
        """Players link nothing — their route is scheduling from the bracket."""
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        match = await _match(t, users)

        with pytest.raises(PermissionError, match='Only staff or a tournament admin'):
            await service.link_match_to_bracket_match(users[0], bmatch.id, match.id)

    async def test_tournament_admin_allowed(self, service):
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        ta = await _player(4400, 'ta')
        await t.admins.add(ta)
        match = await _match(t, users)

        game = await service.link_match_to_bracket_match(ta, bmatch.id, match.id)
        assert game.match_id == match.id


class TestUnlinkMatch:
    async def test_frees_the_slot_and_keeps_the_match(self, service):
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        match = await _match(t, users)
        await service.link_match_to_bracket_match(actor, bmatch.id, match.id)

        assert await service.unlink_match(actor, match.id) is True

        assert not await BracketMatchGame.filter(bracket_match_id=bmatch.id).exists()
        assert await Match.filter(id=match.id).exists()
        assert [m.id for m in await service.list_linkable_matches(t.id)] == [bmatch.id]

    async def test_unlinked_match_reports_false(self, service):
        actor = await _staff()
        t, _, users, _ = await _bracket(service, actor)
        match = await _match(t, users)
        assert await service.unlink_match(actor, match.id) is False

    async def test_played_game_cannot_be_detached(self, service):
        """Detaching a settled game would leave the series short of its own count."""
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        match = await _match(t, users)
        game = await service.link_match_to_bracket_match(actor, bmatch.id, match.id)
        game.state = BracketMatchGameState.COMPLETE
        await game.save()

        with pytest.raises(ValueError, match='already been played'):
            await service.unlink_match(actor, match.id)

    async def test_player_rejected(self, service):
        actor = await _staff()
        t, _, users, bmatch = await _bracket(service, actor)
        match = await _match(t, users)
        await service.link_match_to_bracket_match(actor, bmatch.id, match.id)

        with pytest.raises(PermissionError, match='Only staff or a tournament admin'):
            await service.unlink_match(users[0], match.id)


class TestLinkedMatchAdvancesTheBracket:
    async def test_confirmed_linked_match_advances(self, service):
        """The point of linking: the manual match settles the series."""
        actor = await _staff()
        t, bracket, users, bmatch = await _bracket(service, actor)
        match = await _match(t, users)
        await service.link_match_to_bracket_match(actor, bmatch.id, match.id)

        players = await MatchPlayers.filter(match=match)
        for player in players:
            player.finish_rank = 1 if player.user_id == users[0].id else 2
            await player.save()

        assert await service.advance_if_linked(match, actor) is True

        await bmatch.refresh_from_db()
        assert bmatch.state == BracketMatchState.COMPLETE
        winner = await service.get_bracket_match_for_match(match.id)
        assert winner.winner_id is not None
