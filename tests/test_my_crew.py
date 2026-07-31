"""A volunteer's own record of what they signed up to crew.

Measured before this existed: the Player tab ("Your Schedule") contained no
mention of commentator, tracker or crew; there was no My Commitments anywhere;
and after signing up, the volunteer's only handle on the commitment was a
Withdraw button in one row of a 17-row board — 5,874 px of scroll on a phone.

The service half is exercised against the real schema; the copy half is pure
and tested directly, because the NiceGUI layer has no render coverage.
"""

from datetime import datetime, timedelta, timezone

import pytest

from application.services.crew_service import CrewService
from models import Commentator, Match, Tournament, Tracker, User
from pages.home_tabs.my_crew import commitment_status, commitment_title


class TestCommitmentStatus:
    """The four states one commitment can be in, and what each is called."""

    def test_an_unapproved_signup_is_awaiting_approval(self):
        assert commitment_status({'approved': False})[1] == 'Awaiting approval'

    def test_an_approved_signup_asks_for_a_confirmation(self):
        """The DM asks for it too; a volunteer who missed the DM had no other
        way to give it."""
        _chip, label = commitment_status({'approved': True, 'acknowledged': False})
        assert label == 'Approved — please confirm'

    def test_an_acknowledged_signup_is_settled(self):
        assert commitment_status(
            {'approved': True, 'acknowledged': True})[1] == 'Confirmed'

    def test_a_played_match_reads_as_history_not_as_a_duty(self):
        """Even unapproved: nothing is owed on a match that already happened."""
        assert commitment_status({'approved': False, 'finished': True})[1] == 'Played'

    def test_each_state_gets_its_own_chip(self):
        chips = {
            commitment_status(row)[0] for row in (
                {'approved': False},
                {'approved': True, 'acknowledged': False},
                {'approved': True, 'acknowledged': True},
                {'finished': True},
            )
        }
        assert len(chips) == 4, 'two states rendering the same colour say the same thing'


class TestCommitmentTitle:
    def test_it_names_the_match_not_its_id(self):
        title = commitment_title({
            'players': ['Alice', 'Bob'], 'tournament': 'Cup', 'scheduled_at': None,
            'match_id': 17,
        })
        assert 'Alice vs Bob' in title
        assert '17' not in title

    def test_a_match_with_no_roster_still_says_something(self):
        assert commitment_title({'players': [], 'tournament': 'Cup'}) == 'Cup'


@pytest.fixture
async def person(db):
    return await User.create(discord_id=9100, username='caster')


@pytest.fixture
async def tournament(db):
    return await Tournament.create(name='Cup')


def _at(hours: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


class TestListMyCommitments:
    async def test_nothing_signed_up_is_an_empty_list(self, person, db):
        assert await CrewService().list_my_commitments(person) == []

    async def test_both_roles_appear_in_one_list(self, person, tournament, db):
        one = await Match.create(tournament=tournament, scheduled_at=_at(2))
        two = await Match.create(tournament=tournament, scheduled_at=_at(4))
        await Commentator.create(match=one, user=person, approved=True)
        await Tracker.create(match=two, user=person, approved=False)

        rows = await CrewService().list_my_commitments(person)
        assert [r['role'] for r in rows] == ['commentator', 'tracker']

    async def test_they_are_ordered_by_when_they_happen(self, person, tournament, db):
        """Two models merged into one chronological list — the whole point of
        doing the join in the service rather than the page."""
        later = await Match.create(tournament=tournament, scheduled_at=_at(6))
        sooner = await Match.create(tournament=tournament, scheduled_at=_at(1))
        await Commentator.create(match=later, user=person)
        await Tracker.create(match=sooner, user=person)

        rows = await CrewService().list_my_commitments(person)
        assert [r['match_id'] for r in rows] == [sooner.id, later.id]

    async def test_somebody_elses_signup_is_not_mine(self, person, tournament, db):
        other = await User.create(discord_id=9101, username='someone')
        match = await Match.create(tournament=tournament, scheduled_at=_at(2))
        await Commentator.create(match=match, user=other, approved=True)

        assert await CrewService().list_my_commitments(person) == []

    async def test_past_matches_are_hidden_by_default(self, person, tournament, db):
        past = await Match.create(tournament=tournament, scheduled_at=_at(-30))
        await Commentator.create(match=past, user=person, approved=True)

        assert await CrewService().list_my_commitments(person) == []

    async def test_past_matches_are_available_on_request(self, person, tournament, db):
        past = await Match.create(tournament=tournament, scheduled_at=_at(-30))
        await Commentator.create(match=past, user=person, approved=True)

        rows = await CrewService().list_my_commitments(person, upcoming_only=False)
        assert [r['match_id'] for r in rows] == [past.id]

    async def test_a_row_carries_what_the_card_has_to_show(self, person, tournament, db):
        match = await Match.create(tournament=tournament, scheduled_at=_at(3))
        player = await User.create(discord_id=9102, username='racer')
        await match.players.all()  # ensure the relation is materialised
        from models import MatchPlayers
        await MatchPlayers.create(match=match, user=player)
        await Commentator.create(match=match, user=person, approved=True)

        row = (await CrewService().list_my_commitments(person))[0]
        assert row['tournament'] == 'Cup'
        assert row['players'] == ['racer']
        assert row['approved'] is True
        assert row['acknowledged'] is False
        assert row['finished'] is False
