"""Players privately opting into a match's harder preset.

The rules worth pinning are the ones the feature stops being itself without: a
lone opt-in tells nobody anything, agreement needs everybody, the window shuts
when the seed rolls, and staff's override beats both answers in either
direction.
"""

import itertools

import pytest

from application.events import EventType, event_bus
from application.services import MatchHardPresetService
from application.services.audit_service import AuditActions
from models import (
    AuditLog,
    GeneratedSeeds,
    Match,
    MatchHardPresetOptIn,
    MatchPlayers,
    Preset,
    PresetOverride,
    Tournament,
)
from tests.factories import make_user, utc


@pytest.fixture
def captured_events():
    """Subscribe to the event bus for the test and collect published events."""
    seen = []
    token = event_bus.subscribe_sync(seen.append)
    yield seen
    event_bus.unsubscribe(token)


_preset_seq = itertools.count()
_discord_ids = itertools.count(910000)


async def _presets():
    """A fresh pair per call — presets are unique per (tenant, randomizer, name)."""
    n = next(_preset_seq)
    standard = await Preset.create(
        name=f'Standard {n}', randomizer='alttpr', settings={'mode': 'open'},
    )
    hard = await Preset.create(
        name=f'Hard Mode {n}', randomizer='alttpr',
        settings={'mode': 'open', 'pool': 'hard'},
    )
    return standard, hard


async def _match(*, offers_hard=True, players=2, seeded=False):
    standard, hard = await _presets()
    tournament = await Tournament.create(
        name='T', preset=standard, hard_preset=hard if offers_hard else None,
    )
    seed = None
    if seeded:
        seed = await GeneratedSeeds.create(
            seed_url='https://example.test/seed', randomizer='alttpr', preset=standard,
        )
    match = await Match.create(
        tournament=tournament,
        scheduled_at=utc(2025, 1, 15, 19, 30),
        generated_seed=seed,
    )
    users = []
    for i in range(players):
        user = await make_user(discord_id=next(_discord_ids), username=f'p{i}')
        await MatchPlayers.create(match=match, user=user)
        users.append(user)
    await match.fetch_related('players')
    return match, users


class TestOptingIn:
    async def test_a_player_can_opt_in(self, db, stub_discord_queue):
        match, (p1, _) = await _match()

        state = await MatchHardPresetService().opt_in(match.id, p1)

        assert state.opted_in is True
        assert await MatchHardPresetOptIn.filter(match=match, user=p1).exists()

    async def test_a_non_player_is_refused(self, db, stub_discord_queue):
        match, _ = await _match()
        outsider = await make_user(discord_id=next(_discord_ids), username='nosy')

        with pytest.raises(ValueError, match='players in a match'):
            await MatchHardPresetService().opt_in(match.id, outsider)

    async def test_refused_when_the_tournament_offers_no_harder_preset(
        self, db, stub_discord_queue,
    ):
        match, (p1, _) = await _match(offers_hard=False)

        with pytest.raises(ValueError, match='does not offer a harder preset'):
            await MatchHardPresetService().opt_in(match.id, p1)

    async def test_refused_once_the_seed_is_rolled(self, db, stub_discord_queue):
        """The window shuts at the roll, because the settings are then recorded."""
        match, (p1, _) = await _match(seeded=True)

        with pytest.raises(ValueError, match='already been rolled'):
            await MatchHardPresetService().opt_in(match.id, p1)

    async def test_opting_in_twice_is_harmless(self, db, stub_discord_queue):
        match, (p1, _) = await _match()
        service = MatchHardPresetService()

        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p1)

        assert await MatchHardPresetOptIn.filter(match=match).count() == 1


class TestSecrecy:
    """The reason the feature exists: one opt-in must reach nobody."""

    async def test_my_state_never_reports_the_other_player(
        self, db, stub_discord_queue,
    ):
        match, (p1, p2) = await _match()
        await MatchHardPresetService().opt_in(match.id, p1)

        state = await MatchHardPresetService().my_state(match, p2)

        assert state.opted_in is False
        assert state.everyone_in is False

    async def test_a_lone_opt_in_is_indistinguishable_from_none(
        self, db, stub_discord_queue,
    ):
        """p2's view of "p1 opted in" must equal their view of "nobody did"."""
        opted, (p1, p2) = await _match()
        await MatchHardPresetService().opt_in(opted.id, p1)
        untouched, (_, other_p2) = await _match()

        seen = await MatchHardPresetService().my_state(opted, p2)
        control = await MatchHardPresetService().my_state(untouched, other_p2)

        assert (seen.opted_in, seen.everyone_in) == (control.opted_in, control.everyone_in)

    async def test_a_lone_opt_in_publishes_no_event(
        self, db, stub_discord_queue, captured_events,
    ):
        """A webhook subscriber is an outside listener, so it hears nothing."""
        match, (p1, _) = await _match()

        await MatchHardPresetService().opt_in(match.id, p1)

        assert captured_events == []

    async def test_a_lone_opt_in_sends_no_dm(self, db, stub_discord_queue):
        match, (p1, _) = await _match()

        await MatchHardPresetService().opt_in(match.id, p1)

        assert stub_discord_queue == []

    async def test_a_lone_opt_in_is_still_audited(self, db, stub_discord_queue):
        """Staff read their own community's history; the players do not."""
        match, (p1, _) = await _match()

        await MatchHardPresetService().opt_in(match.id, p1)

        assert await AuditLog.filter(
            action=AuditActions.MATCH_HARD_PRESET_OPTED_IN,
        ).exists()


class TestAgreement:
    async def test_everyone_opting_in_agrees(self, db, stub_discord_queue):
        match, (p1, p2) = await _match()
        service = MatchHardPresetService()

        await service.opt_in(match.id, p1)
        state = await service.opt_in(match.id, p2)

        assert state.everyone_in is True

    async def test_agreement_publishes_and_dms(
        self, db, stub_discord_queue, captured_events,
    ):
        match, (p1, p2) = await _match()
        service = MatchHardPresetService()

        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)

        assert [e.event_type for e in captured_events] == [
            EventType.MATCH_HARD_PRESET_AGREED,
        ]
        assert len(stub_discord_queue) == 1

    async def test_a_three_player_match_needs_all_three(self, db, stub_discord_queue):
        match, users = await _match(players=3)
        service = MatchHardPresetService()

        await service.opt_in(match.id, users[0])
        state = await service.opt_in(match.id, users[1])
        assert state.everyone_in is False

        state = await service.opt_in(match.id, users[2])
        assert state.everyone_in is True

    async def test_backing_out_breaks_the_agreement(
        self, db, stub_discord_queue, captured_events,
    ):
        match, (p1, p2) = await _match()
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)
        captured_events.clear()

        state = await service.withdraw(match.id, p1)

        assert state.opted_in is False
        assert [e.event_type for e in captured_events] == [
            EventType.MATCH_HARD_PRESET_AGREEMENT_REVOKED,
        ]

    async def test_a_match_with_no_players_never_agrees(self, db, stub_discord_queue):
        """An empty roster must not satisfy "everyone opted in" vacuously."""
        match, _ = await _match(players=0)

        assert await MatchHardPresetService()._is_unanimous(match) is False


class TestResolvePreset:
    async def test_unanimous_rolls_the_hard_preset(self, db, stub_discord_queue):
        match, (p1, p2) = await _match()
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)

        preset = await service.resolve_preset(match)

        assert preset.name.startswith('Hard Mode')

    async def test_a_lone_opt_in_rolls_the_standard_preset(
        self, db, stub_discord_queue,
    ):
        match, (p1, _) = await _match()
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)

        preset = await service.resolve_preset(match)

        assert preset.name.startswith('Standard')

    async def test_no_opt_ins_roll_the_standard_preset(self, db, stub_discord_queue):
        match, _ = await _match()

        preset = await MatchHardPresetService().resolve_preset(match)

        assert preset.name.startswith('Standard')


class TestStaffOverride:
    async def test_forcing_hard_beats_no_opt_ins(self, db, stub_discord_queue):
        match, _ = await _match()
        staff = await make_user(discord_id=next(_discord_ids), username='staff')
        service = MatchHardPresetService()

        await service.set_override(match.id, PresetOverride.HARD, staff)
        await match.refresh_from_db()
        await match.fetch_related('tournament', 'tournament__preset', 'tournament__hard_preset')

        assert (await service.resolve_preset(match)).name.startswith('Hard Mode')

    async def test_forcing_standard_beats_a_unanimous_agreement(
        self, db, stub_discord_queue,
    ):
        match, (p1, p2) = await _match()
        staff = await make_user(discord_id=next(_discord_ids), username='staff')
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)

        await service.set_override(match.id, PresetOverride.STANDARD, staff)
        await match.refresh_from_db()
        await match.fetch_related('tournament', 'tournament__preset', 'tournament__hard_preset')

        assert (await service.resolve_preset(match)).name.startswith('Standard')

    async def test_an_override_keeps_the_opt_ins(self, db, stub_discord_queue):
        """Clearing it must restore what the players chose, not a blank slate."""
        match, (p1, p2) = await _match()
        staff = await make_user(discord_id=next(_discord_ids), username='staff')
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)

        await service.set_override(match.id, PresetOverride.STANDARD, staff)
        await service.set_override(match.id, None, staff)
        await match.refresh_from_db()
        await match.fetch_related('tournament', 'tournament__preset', 'tournament__hard_preset')

        assert (await service.resolve_preset(match)).name.startswith('Hard Mode')

    async def test_players_cannot_opt_in_under_an_override(
        self, db, stub_discord_queue,
    ):
        match, (p1, _) = await _match()
        staff = await make_user(discord_id=next(_discord_ids), username='staff')
        service = MatchHardPresetService()
        await service.set_override(match.id, PresetOverride.STANDARD, staff)

        with pytest.raises(ValueError, match='Staff have already chosen'):
            await service.opt_in(match.id, p1)

    async def test_refused_once_the_seed_is_rolled(self, db, stub_discord_queue):
        match, _ = await _match(seeded=True)
        staff = await make_user(discord_id=next(_discord_ids), username='staff')

        with pytest.raises(ValueError, match='already been rolled'):
            await MatchHardPresetService().set_override(
                match.id, PresetOverride.HARD, staff,
            )

    async def test_forcing_hard_without_a_hard_preset_is_refused(
        self, db, stub_discord_queue,
    ):
        match, _ = await _match(offers_hard=False)
        staff = await make_user(discord_id=next(_discord_ids), username='staff')

        with pytest.raises(ValueError, match='does not have a harder preset'):
            await MatchHardPresetService().set_override(
                match.id, PresetOverride.HARD, staff,
            )


class TestRosterChanges:
    async def test_a_departing_player_stops_counting(self, db, stub_discord_queue):
        match, (p1, p2) = await _match()
        staff = await make_user(discord_id=next(_discord_ids), username='staff')
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)

        await service.drop_for_removed_players(
            match, [p1.id], staff, was_unanimous=True,
        )

        assert not await MatchHardPresetOptIn.filter(match=match, user=p2).exists()

    async def test_swapping_a_player_revokes_the_agreement(
        self, db, stub_discord_queue, captured_events,
    ):
        """A stale yes must not survive the roster that produced it."""
        match, (p1, p2) = await _match()
        staff = await make_user(discord_id=next(_discord_ids), username='staff')
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)
        captured_events.clear()

        replacement = await make_user(discord_id=next(_discord_ids), username='sub')
        await MatchPlayers.filter(match=match, user=p2).delete()
        await MatchPlayers.create(match=match, user=replacement)
        await match.fetch_related('players')
        await service.drop_for_removed_players(
            match, [p1.id, replacement.id], staff, was_unanimous=True,
        )

        assert [e.event_type for e in captured_events] == [
            EventType.MATCH_HARD_PRESET_AGREEMENT_REVOKED,
        ]

    async def test_a_swap_that_keeps_everyone_in_does_not_revoke(
        self, db, stub_discord_queue, captured_events,
    ):
        """Only a broken agreement is announced, not every roster edit."""
        match, (p1, p2) = await _match()
        staff = await make_user(discord_id=next(_discord_ids), username='staff')
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)
        captured_events.clear()

        await service.drop_for_removed_players(
            match, [p1.id, p2.id], staff, was_unanimous=True,
        )

        assert captured_events == []


class TestRosterChangeSecrecy:
    """A roster edit must not tell a new player what the old ones chose."""

    async def test_a_newly_added_player_is_not_told_the_others_had_agreed(
        self, db, stub_discord_queue,
    ):
        """The added player never held a row, so the agreement is not theirs to
        hear about — and hearing it would name their opponents' opt-ins and
        mark them the sole holdout, which is the pressure the whole feature
        exists to prevent."""
        match, (p1, p2) = await _match()
        staff = await make_user(discord_id=next(_discord_ids), username='staff')
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)
        stub_discord_queue.clear()

        newcomer = await make_user(discord_id=next(_discord_ids), username='newcomer')
        await MatchPlayers.create(match=match, user=newcomer)
        await match.fetch_related('players')
        await service.drop_for_removed_players(
            match, [p1.id, p2.id, newcomer.id], staff, was_unanimous=True,
        )

        assert len(stub_discord_queue) == 1
        recipients = stub_discord_queue[0].cr_frame.f_locals['recipients']
        names = {u.preferred_name for u in recipients}
        assert names == {p1.preferred_name, p2.preferred_name}
        assert newcomer.preferred_name not in names

    async def test_dropping_the_holdout_completes_the_agreement(
        self, db, stub_discord_queue, captured_events,
    ):
        """The mirror case: a shrink can create unanimity, and what a match
        rolls must not change without an event or a word to the players."""
        match, (p1, p2) = await _match()
        staff = await make_user(discord_id=next(_discord_ids), username='staff')
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        captured_events.clear()
        stub_discord_queue.clear()

        await MatchPlayers.filter(match=match, user=p2).delete()
        await match.fetch_related('players')
        await service.drop_for_removed_players(
            match, [p1.id], staff, was_unanimous=False,
        )

        assert [e.event_type for e in captured_events] == [
            EventType.MATCH_HARD_PRESET_AGREED,
        ]
        assert len(stub_discord_queue) == 1
        assert (await service.resolve_preset(match)).name.startswith('Hard Mode')


class TestBoardStates:
    async def test_reports_only_the_viewers_own_rows(self, db, stub_discord_queue):
        match, (p1, p2) = await _match()
        await MatchHardPresetService().opt_in(match.id, p1)

        states = await MatchHardPresetService().board_states(p2, [match.id])

        assert states[match.id].opted_in is False
        assert states[match.id].everyone_in is False

    async def test_matches_the_single_row_read(self, db, stub_discord_queue):
        """The bulk path and ``my_state`` must not disagree about a viewer."""
        match, (p1, p2) = await _match()
        service = MatchHardPresetService()
        await service.opt_in(match.id, p1)
        await service.opt_in(match.id, p2)

        bulk = (await service.board_states(p1, [match.id]))[match.id]
        single = await service.my_state(match, p1)

        assert (bulk.opted_in, bulk.everyone_in) == (single.opted_in, single.everyone_in)

    async def test_a_tournament_without_a_hard_preset_offers_nothing(
        self, db, stub_discord_queue,
    ):
        match, (p1, _) = await _match(offers_hard=False)

        states = await MatchHardPresetService().board_states(p1, [match.id])

        assert states == {}
