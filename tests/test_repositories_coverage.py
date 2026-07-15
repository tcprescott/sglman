"""Direct unit tests for the repository (data-access) layer.

These exercise the query/CRUD/filter/ordering/prefetch behavior of the
repositories in isolation against the in-memory SQLite ``db`` fixture.
Repositories perform no Discord I/O, so no queue stub is needed.
"""

from datetime import date, datetime, timezone

from application.repositories.match_acknowledgment_repository import MatchAcknowledgmentRepository
from application.repositories.match_repository import MatchRepository
from application.repositories.tournament_notification_repository import TournamentNotificationRepository
from application.repositories.tournament_repository import TournamentRepository
from application.repositories.user_repository import UserRepository
from application.repositories.user_role_repository import UserRoleRepository
from models import (
    Match,
    MatchAcknowledgment,
    MatchNotificationLevel,
    Role,
    RoleSource,
    StreamRoom,
    Tournament,
    TournamentNotificationPreference,
    TournamentPlayers,
    User,
    UserRole,
)

UTC = timezone.utc


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


async def make_user(discord_id: int, username: str, **kwargs) -> User:
    return await User.create(discord_id=discord_id, username=username, **kwargs)


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------


class TestUserRepository:
    async def test_get_by_id_and_discord_id(self, db):
        u = await make_user(1, "alice")
        assert (await UserRepository.get_by_id(u.id)).id == u.id
        assert (await UserRepository.get_by_discord_id(1)).id == u.id
        assert await UserRepository.get_by_id(9999) is None
        assert await UserRepository.get_by_discord_id(424242) is None

    async def test_get_all_orders_by_username(self, db):
        await make_user(1, "charlie")
        await make_user(2, "alice")
        await make_user(3, "bob")
        users = await UserRepository.get_all()
        assert [u.username for u in users] == ["alice", "bob", "charlie"]

    async def test_get_all_filters_by_role_distinct(self, db):
        u1 = await make_user(1, "alice")
        u2 = await make_user(2, "bob")
        await UserRole.create(user=u1, role=Role.STAFF)
        # A user with the role twice-over (different roles) should not duplicate.
        await UserRole.create(user=u1, role=Role.PROCTOR)
        await UserRole.create(user=u2, role=Role.PROCTOR)

        staff = await UserRepository.get_all(role=Role.STAFF)
        assert [u.id for u in staff] == [u1.id]

        proctors = await UserRepository.get_all(role=Role.PROCTOR)
        assert {u.id for u in proctors} == {u1.id, u2.id}

    async def test_get_all_has_discord_returns_users(self, db):
        # ``discord_id`` is a required, unique column, so the ``exclude(discord_id=None)``
        # branch can never drop a real row — it is effectively a no-op given the schema.
        # The test still drives the branch and asserts the created user comes back.
        u = await make_user(1, "alice")
        users = await UserRepository.get_all(has_discord=True)
        assert [x.id for x in users] == [u.id]

    async def test_search_by_name_returns_matches(self, db):
        await make_user(1, "alice", display_name="Alice Wonder")
        results = await UserRepository.search_by_name("ali")
        assert any(u.username == "alice" for u in results)

    async def test_search_by_name_matches_display_name(self, db):
        await make_user(1, "xyz", display_name="Alice Wonder")
        results = await UserRepository.search_by_name("wonder")
        assert any(u.username == "xyz" for u in results)

    async def test_create_sets_fields(self, db):
        u = await UserRepository.create(
            username="dave", discord_id=77, display_name="Dave", pronouns="he/him", is_active=False
        )
        assert u.username == "dave"
        assert u.discord_id == 77
        assert u.display_name == "Dave"
        assert u.pronouns == "he/him"
        assert u.is_active is False

    async def test_get_or_create_by_discord_id(self, db):
        user, created = await UserRepository.get_or_create_by_discord_id(555, "newbie")
        assert created is True
        assert user.discord_id == 555
        again, created2 = await UserRepository.get_or_create_by_discord_id(555, "ignored")
        assert created2 is False
        assert again.id == user.id
        assert again.username == "newbie"

    async def test_update_sets_fields_and_persists(self, db):
        u = await make_user(1, "alice")
        await UserRepository.update(u, username="alice2", is_active=False)
        refreshed = await User.get(id=u.id)
        assert refreshed.username == "alice2"
        assert refreshed.is_active is False

    async def test_delete_removes_row(self, db):
        u = await make_user(1, "alice")
        await UserRepository.delete(u)
        assert await User.get_or_none(id=u.id) is None

    async def test_update_discord_info_all_fields(self, db):
        u = await make_user(1, "alice")
        await UserRepository.update_discord_info(u, username="alice_dc", discriminator="0001", avatar="abc")
        refreshed = await User.get(id=u.id)
        # username is a real column and persists.
        assert refreshed.username == "alice_dc"
        # discriminator/avatar are NOT model fields (documented in data-model.md):
        # they are assigned to the in-memory instance but silently dropped on save,
        # so the reloaded row never gains them.
        assert u.discriminator == "0001"  # in-memory only
        assert not hasattr(refreshed, "discriminator")  # never persisted
        assert not hasattr(refreshed, "avatar")

    async def test_update_discord_info_optional_fields_skipped(self, db):
        u = await make_user(1, "alice")
        await UserRepository.update_discord_info(u, username="renamed")
        assert (await User.get(id=u.id)).username == "renamed"
        # None args leave the non-field attributes entirely unset.
        assert not hasattr(u, "discriminator")
        assert not hasattr(u, "avatar")


# ---------------------------------------------------------------------------
# UserRoleRepository
# ---------------------------------------------------------------------------


class TestUserRoleRepository:
    async def test_add_creates_new_role(self, db):
        u = await make_user(1, "alice")
        granter = await make_user(2, "granter")
        ur = await UserRoleRepository.add(u, Role.STAFF, granted_by=granter, source=RoleSource.MANUAL)
        assert ur.role == Role.STAFF
        assert ur.source == RoleSource.MANUAL
        assert (await ur.granted_by).id == granter.id

    async def test_add_defaults_to_manual_source(self, db):
        u = await make_user(1, "alice")
        ur = await UserRoleRepository.add(u, Role.PROCTOR)
        assert ur.source == RoleSource.MANUAL

    async def test_manual_grant_pins_a_discord_role(self, db):
        u = await make_user(1, "alice")
        granter = await make_user(2, "granter")
        # Pre-existing Discord-sourced role.
        await UserRole.create(user=u, role=Role.STAFF, source=RoleSource.DISCORD)
        ur = await UserRoleRepository.add(u, Role.STAFF, granted_by=granter, source=RoleSource.MANUAL)
        assert ur.source == RoleSource.MANUAL
        assert (await ur.granted_by).id == granter.id
        # Persisted, not just in-memory.
        refreshed = await UserRole.get(id=ur.id)
        assert refreshed.source == RoleSource.MANUAL

    async def test_add_existing_discord_role_again_does_not_pin(self, db):
        u = await make_user(1, "alice")
        await UserRole.create(user=u, role=Role.STAFF, source=RoleSource.DISCORD)
        ur = await UserRoleRepository.add(u, Role.STAFF, source=RoleSource.DISCORD)
        # A Discord re-sync must not flip the source to MANUAL.
        assert ur.source == RoleSource.DISCORD

    async def test_remove_returns_deleted_count(self, db):
        u = await make_user(1, "alice")
        await UserRole.create(user=u, role=Role.STAFF)
        deleted = await UserRoleRepository.remove(u, Role.STAFF)
        assert deleted == 1
        assert await UserRoleRepository.remove(u, Role.STAFF) == 0

    async def test_list_for_user(self, db):
        u = await make_user(1, "alice")
        other = await make_user(2, "bob")
        await UserRole.create(user=u, role=Role.STAFF)
        await UserRole.create(user=u, role=Role.PROCTOR)
        await UserRole.create(user=other, role=Role.VOLUNTEER)
        rows = await UserRoleRepository.list_for_user(u)
        assert {r.role for r in rows} == {Role.STAFF, Role.PROCTOR}

    async def test_list_for_user_by_source(self, db):
        u = await make_user(1, "alice")
        await UserRole.create(user=u, role=Role.STAFF, source=RoleSource.MANUAL)
        await UserRole.create(user=u, role=Role.PROCTOR, source=RoleSource.DISCORD)
        manual = await UserRoleRepository.list_for_user_by_source(u, RoleSource.MANUAL)
        assert {r.role for r in manual} == {Role.STAFF}
        discord = await UserRoleRepository.list_for_user_by_source(u, RoleSource.DISCORD)
        assert {r.role for r in discord} == {Role.PROCTOR}

    async def test_list_users_with_role(self, db):
        u1 = await make_user(1, "alice")
        u2 = await make_user(2, "bob")
        await make_user(3, "carol")
        await UserRole.create(user=u1, role=Role.STAFF)
        await UserRole.create(user=u2, role=Role.STAFF)
        users = await UserRoleRepository.list_users_with_role(Role.STAFF)
        assert {u.id for u in users} == {u1.id, u2.id}
        assert await UserRoleRepository.list_users_with_role(Role.EQUIPMENT_MANAGER) == []


# ---------------------------------------------------------------------------
# MatchAcknowledgmentRepository
# ---------------------------------------------------------------------------


class TestMatchAcknowledgmentRepository:
    async def _match(self) -> Match:
        t = await Tournament.create(name="T")
        return await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))

    async def test_list_for_match(self, db):
        m = await self._match()
        u1 = await make_user(1, "alice")
        u2 = await make_user(2, "bob")
        await MatchAcknowledgment.create(match=m, user=u1, acknowledged_at=utc(2025, 1, 1))
        await MatchAcknowledgment.create(match=m, user=u2)
        rows = await MatchAcknowledgmentRepository.list_for_match(m)
        assert len(rows) == 2
        # ``user`` prefetched — accessing without an extra await works.
        assert {r.user.username for r in rows} == {"alice", "bob"}

    async def test_list_for_matches_empty_input(self, db):
        assert await MatchAcknowledgmentRepository.list_for_matches([]) == {}

    async def test_list_for_matches_groups_by_match(self, db):
        t = await Tournament.create(name="T")
        m1 = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        m2 = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 2, 12))
        m3 = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 3, 12))
        u = await make_user(1, "alice")
        await MatchAcknowledgment.create(match=m1, user=u)
        await MatchAcknowledgment.create(match=m2, user=u)
        result = await MatchAcknowledgmentRepository.list_for_matches([m1.id, m2.id, m3.id])
        assert set(result.keys()) == {m1.id, m2.id, m3.id}
        assert len(result[m1.id]) == 1
        assert len(result[m2.id]) == 1
        # A requested match with no acks is present with an empty list.
        assert result[m3.id] == []

    async def test_get_returns_row_or_none(self, db):
        m = await self._match()
        u = await make_user(1, "alice")
        assert await MatchAcknowledgmentRepository.get(m, u) is None
        await MatchAcknowledgment.create(match=m, user=u)
        found = await MatchAcknowledgmentRepository.get(m, u)
        assert found is not None
        assert (await found.user).id == u.id

    async def test_upsert_acknowledged_then_cleared(self, db):
        m = await self._match()
        u = await make_user(1, "alice")
        ack = await MatchAcknowledgmentRepository.upsert(m, u, acknowledged=True, auto=True)
        assert ack.acknowledged_at is not None
        assert ack.auto_acknowledged is True
        # Re-upsert with acknowledged=False clears the timestamp and auto flag.
        ack2 = await MatchAcknowledgmentRepository.upsert(m, u, acknowledged=False, auto=True)
        assert ack2.acknowledged_at is None
        assert ack2.auto_acknowledged is False
        assert ack2.id == ack.id

    async def test_delete_for_match(self, db):
        m = await self._match()
        u1 = await make_user(1, "alice")
        u2 = await make_user(2, "bob")
        await MatchAcknowledgment.create(match=m, user=u1)
        await MatchAcknowledgment.create(match=m, user=u2)
        deleted = await MatchAcknowledgmentRepository.delete_for_match(m)
        assert deleted == 2
        assert await MatchAcknowledgment.filter(match=m).count() == 0

    async def test_delete_for_user(self, db):
        m = await self._match()
        u1 = await make_user(1, "alice")
        u2 = await make_user(2, "bob")
        await MatchAcknowledgment.create(match=m, user=u1)
        await MatchAcknowledgment.create(match=m, user=u2)
        await MatchAcknowledgmentRepository.delete_for_user(m, u1)
        remaining = await MatchAcknowledgment.filter(match=m)
        assert [(await r.user).id for r in remaining] == [u2.id]


# ---------------------------------------------------------------------------
# TournamentNotificationRepository
# ---------------------------------------------------------------------------


class TestTournamentNotificationRepository:
    def setup_method(self):
        self.repo = TournamentNotificationRepository()

    async def test_get_by_user_and_tournament(self, db):
        u = await make_user(1, "alice")
        t = await Tournament.create(name="T")
        assert await self.repo.get_by_user_and_tournament(u, t) is None
        pref = await TournamentNotificationPreference.create(
            user=u, tournament=t, match_notifications=MatchNotificationLevel.ALL
        )
        found = await self.repo.get_by_user_and_tournament(u, t)
        assert found.id == pref.id

    async def test_get_all_for_user_prefetches_tournament(self, db):
        u = await make_user(1, "alice")
        t1 = await Tournament.create(name="A")
        t2 = await Tournament.create(name="B")
        other = await make_user(2, "bob")
        await TournamentNotificationPreference.create(user=u, tournament=t1)
        await TournamentNotificationPreference.create(user=u, tournament=t2)
        await TournamentNotificationPreference.create(user=other, tournament=t1)
        rows = await self.repo.get_all_for_user(u)
        assert {r.tournament.name for r in rows} == {"A", "B"}

    async def test_upsert_creates_then_updates(self, db):
        u = await make_user(1, "alice")
        t = await Tournament.create(name="T")
        pref = await self.repo.upsert(u, t, MatchNotificationLevel.STREAMED)
        assert pref.match_notifications == MatchNotificationLevel.STREAMED
        pref2 = await self.repo.upsert(u, t, MatchNotificationLevel.ALL)
        assert pref2.id == pref.id
        assert pref2.match_notifications == MatchNotificationLevel.ALL

    async def test_match_subscribers_with_stream_room(self, db):
        t = await Tournament.create(name="T")
        u_all = await make_user(1, "all_user")
        u_streamed = await make_user(2, "streamed_user")
        u_candidates = await make_user(3, "candidate_user")
        u_none = await make_user(4, "none_user")
        u_no_dm = await make_user(5, "no_dm", dm_notifications=False)
        await TournamentNotificationPreference.create(
            user=u_all, tournament=t, match_notifications=MatchNotificationLevel.ALL
        )
        await TournamentNotificationPreference.create(
            user=u_streamed, tournament=t, match_notifications=MatchNotificationLevel.STREAMED
        )
        await TournamentNotificationPreference.create(
            user=u_candidates, tournament=t, match_notifications=MatchNotificationLevel.STREAMED_AND_CANDIDATES
        )
        await TournamentNotificationPreference.create(
            user=u_none, tournament=t, match_notifications=MatchNotificationLevel.NONE
        )
        await TournamentNotificationPreference.create(
            user=u_no_dm, tournament=t, match_notifications=MatchNotificationLevel.ALL
        )
        subs = await self.repo.get_match_notification_subscribers(t.id, has_stream_room=True)
        ids = {u.id for u in subs}
        # ALL/STREAMED/CANDIDATES qualify when there's a stream room; NONE and
        # dm_notifications=False are excluded.
        assert ids == {u_all.id, u_streamed.id, u_candidates.id}

    async def test_match_subscribers_without_stream_room(self, db):
        t = await Tournament.create(name="T")
        u_all = await make_user(1, "all_user")
        u_streamed = await make_user(2, "streamed_user")
        await TournamentNotificationPreference.create(
            user=u_all, tournament=t, match_notifications=MatchNotificationLevel.ALL
        )
        await TournamentNotificationPreference.create(
            user=u_streamed, tournament=t, match_notifications=MatchNotificationLevel.STREAMED
        )
        subs = await self.repo.get_match_notification_subscribers(t.id, has_stream_room=False)
        # Only 'all' subscribers qualify with no stream room.
        assert {u.id for u in subs} == {u_all.id}

    async def test_stream_candidate_subscribers(self, db):
        t = await Tournament.create(name="T")
        u_candidate = await make_user(1, "candidate")
        u_streamed = await make_user(2, "streamed")
        u_no_dm = await make_user(3, "no_dm", dm_notifications=False)
        await TournamentNotificationPreference.create(
            user=u_candidate, tournament=t, match_notifications=MatchNotificationLevel.STREAMED_AND_CANDIDATES
        )
        await TournamentNotificationPreference.create(
            user=u_streamed, tournament=t, match_notifications=MatchNotificationLevel.STREAMED
        )
        await TournamentNotificationPreference.create(
            user=u_no_dm, tournament=t, match_notifications=MatchNotificationLevel.STREAMED_AND_CANDIDATES
        )
        subs = await self.repo.get_stream_candidate_subscribers(t.id)
        assert {u.id for u in subs} == {u_candidate.id}


# ---------------------------------------------------------------------------
# TournamentRepository
# ---------------------------------------------------------------------------


class TestTournamentRepository:
    async def test_get_by_id_with_and_without_prefetch(self, db):
        t = await Tournament.create(name="T")
        u = await make_user(1, "alice")
        await TournamentPlayers.create(tournament=t, user=u)
        plain = await TournamentRepository.get_by_id(t.id)
        assert plain.id == t.id
        with_players = await TournamentRepository.get_by_id(t.id, prefetch_players=True)
        assert [p.user.username for p in with_players.players] == ["alice"]
        assert await TournamentRepository.get_by_id(9999) is None

    async def test_get_by_ids_ordered_by_name(self, db):
        t1 = await Tournament.create(name="Charlie")
        t2 = await Tournament.create(name="Alpha")
        t3 = await Tournament.create(name="Bravo")
        result = await TournamentRepository.get_by_ids([t1.id, t2.id, t3.id])
        assert [t.name for t in result] == ["Alpha", "Bravo", "Charlie"]

    async def test_get_all_filters(self, db):
        active_staff = await Tournament.create(name="A", is_active=True, staff_administered=True)
        inactive = await Tournament.create(name="B", is_active=False, staff_administered=False)
        active_nonstaff = await Tournament.create(name="C", is_active=True, staff_administered=False)

        all_t = await TournamentRepository.get_all()
        assert [t.name for t in all_t] == ["A", "B", "C"]

        active = await TournamentRepository.get_all(active_only=True)
        assert {t.id for t in active} == {active_staff.id, active_nonstaff.id}

        staff = await TournamentRepository.get_all(staff_only=True)
        assert {t.id for t in staff} == {active_staff.id}

        _ = inactive  # referenced for clarity

    async def test_get_all_prefetch_players(self, db):
        t = await Tournament.create(name="A")
        u = await make_user(1, "alice")
        await TournamentPlayers.create(tournament=t, user=u)
        result = await TournamentRepository.get_all(prefetch_players=True)
        assert [p.user.username for p in result[0].players] == ["alice"]

    async def test_get_all_as_dict(self, db):
        t1 = await Tournament.create(name="Alpha")
        t2 = await Tournament.create(name="Bravo", is_active=False)
        mapping = await TournamentRepository.get_all_as_dict()
        assert mapping == {t1.id: "Alpha", t2.id: "Bravo"}
        active = await TournamentRepository.get_all_as_dict(active_only=True)
        assert active == {t1.id: "Alpha"}

    async def test_create_sets_fields(self, db):
        t = await TournamentRepository.create(
            name="New",
            description="desc",
            seed_generator="alttpr",
            is_active=False,
            players_per_match=4,
            team_size=2,
            bracket_url="http://b",
            rules_url="http://r",
            tournament_format="single elim",
            triforce_access_message="hi",
            average_match_duration=30,
            max_match_duration=60,
            staff_administered=True,
        )
        assert t.name == "New"
        assert t.seed_generator == "alttpr"
        assert t.is_active is False
        assert t.players_per_match == 4
        assert t.team_size == 2
        assert t.staff_administered is True
        assert t.average_match_duration == 30

    async def test_update_persists(self, db):
        t = await Tournament.create(name="Old")
        await TournamentRepository.update(t, name="Renamed", is_active=False)
        refreshed = await Tournament.get(id=t.id)
        assert refreshed.name == "Renamed"
        assert refreshed.is_active is False

    async def test_delete(self, db):
        t = await Tournament.create(name="Doomed")
        await TournamentRepository.delete(t)
        assert await Tournament.get_or_none(id=t.id) is None

    async def test_enroll_and_unenroll_player(self, db):
        t = await Tournament.create(name="T")
        u = await make_user(1, "alice")
        tp = await TournamentRepository.enroll_player(t, u)
        assert tp.id is not None
        assert await TournamentRepository.is_player_enrolled(t, u) is True
        await TournamentRepository.unenroll_player(t, u)
        assert await TournamentRepository.is_player_enrolled(t, u) is False

    async def test_enroll_player_by_id_and_check(self, db):
        t = await Tournament.create(name="T")
        u = await make_user(1, "alice")
        assert await TournamentRepository.is_player_enrolled_by_id(t.id, u) is False
        await TournamentRepository.enroll_player_by_id(t.id, u)
        assert await TournamentRepository.is_player_enrolled_by_id(t.id, u) is True

    async def test_get_enrolled_players(self, db):
        t = await Tournament.create(name="T")
        u1 = await make_user(1, "alice")
        u2 = await make_user(2, "bob")
        await TournamentPlayers.create(tournament=t, user=u1)
        await TournamentPlayers.create(tournament=t, user=u2)
        rows = await TournamentRepository.get_enrolled_players(t)
        assert {r.user.username for r in rows} == {"alice", "bob"}

    async def test_get_enrolled_players_by_user(self, db):
        t1 = await Tournament.create(name="A")
        t2 = await Tournament.create(name="B")
        u = await make_user(1, "alice")
        await TournamentPlayers.create(tournament=t1, user=u)
        await TournamentPlayers.create(tournament=t2, user=u)
        rows = await TournamentRepository.get_enrolled_players_by_user(u)
        assert {r.tournament.name for r in rows} == {"A", "B"}

    async def test_get_enrolled_players_by_tournament_id(self, db):
        t = await Tournament.create(name="T")
        u = await make_user(1, "alice")
        await TournamentPlayers.create(tournament=t, user=u)
        rows = await TournamentRepository.get_enrolled_players_by_tournament_id(t.id)
        assert [r.user.username for r in rows] == ["alice"]


# ---------------------------------------------------------------------------
# MatchRepository
# ---------------------------------------------------------------------------


class TestMatchRepository:
    async def test_get_by_id_prefetch_and_plain(self, db):
        t = await Tournament.create(name="T")
        u = await make_user(1, "alice")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        await MatchRepository.add_player(m, u)
        prefetched = await MatchRepository.get_by_id(m.id)
        assert [p.user.username for p in prefetched.players] == ["alice"]
        plain = await MatchRepository.get_by_id(m.id, prefetch_relations=False)
        assert plain.id == m.id
        assert await MatchRepository.get_by_id(9999) is None

    async def test_get_all_no_filters_orders_by_scheduled_at(self, db):
        t = await Tournament.create(name="T")
        late = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 3, 12))
        early = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        result = await MatchRepository.get_all(prefetch_relations=False)
        assert [m.id for m in result] == [early.id, late.id]

    async def test_get_all_prefetches_relations_by_default(self, db):
        t = await Tournament.create(name="T")
        u = await make_user(1, "alice")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        await MatchRepository.add_player(m, u)
        result = await MatchRepository.get_all()
        assert [p.user.username for p in result[0].players] == ["alice"]
        assert result[0].tournament.name == "T"

    async def test_get_all_only_upcoming(self, db):
        t = await Tournament.create(name="T")
        open_match = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        await Match.create(tournament=t, scheduled_at=utc(2025, 1, 2, 12), finished_at=utc(2025, 1, 2, 14))
        result = await MatchRepository.get_all(only_upcoming=True, prefetch_relations=False)
        assert [m.id for m in result] == [open_match.id]

    async def test_get_all_filter_by_tournament_ids(self, db):
        t1 = await Tournament.create(name="A")
        t2 = await Tournament.create(name="B")
        m1 = await Match.create(tournament=t1, scheduled_at=utc(2025, 1, 1, 12))
        await Match.create(tournament=t2, scheduled_at=utc(2025, 1, 2, 12))
        result = await MatchRepository.get_all(tournament_ids=[t1.id], prefetch_relations=False)
        assert [m.id for m in result] == [m1.id]

    async def test_get_all_filter_by_stream_room_ids(self, db):
        t = await Tournament.create(name="T")
        sr = await StreamRoom.create(name="Room 1")
        m1 = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12), stream_room=sr)
        await Match.create(tournament=t, scheduled_at=utc(2025, 1, 2, 12))
        result = await MatchRepository.get_all(stream_room_ids=[sr.id], prefetch_relations=False)
        assert [m.id for m in result] == [m1.id]

    async def test_get_all_filter_by_user_discord_id(self, db):
        t = await Tournament.create(name="T")
        u = await make_user(111, "alice")
        m1 = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        await Match.create(tournament=t, scheduled_at=utc(2025, 1, 2, 12))
        await MatchRepository.add_player(m1, u)
        result = await MatchRepository.get_all(user_discord_id=111, prefetch_relations=False)
        assert [m.id for m in result] == [m1.id]

    async def test_create_sets_fields(self, db):
        t = await Tournament.create(name="T")
        sr = await StreamRoom.create(name="Room 1")
        m = await MatchRepository.create(
            tournament_id=t.id,
            scheduled_at=utc(2025, 1, 1, 12),
            comment="hi",
            stream_room_id=sr.id,
            is_stream_candidate=True,
        )
        assert m.tournament_id == t.id
        assert m.comment == "hi"
        assert m.stream_room_id == sr.id
        assert m.is_stream_candidate is True

    async def test_update_persists(self, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        returned = await MatchRepository.update(m, comment="updated", is_stream_candidate=True)
        assert returned.comment == "updated"
        refreshed = await Match.get(id=m.id)
        assert refreshed.comment == "updated"
        assert refreshed.is_stream_candidate is True

    async def test_delete(self, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        await MatchRepository.delete(m)
        assert await Match.get_or_none(id=m.id) is None

    async def test_add_and_get_players(self, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        u1 = await make_user(1, "alice")
        u2 = await make_user(2, "bob")
        await MatchRepository.add_player(m, u1)
        await MatchRepository.add_player(m, u2)
        by_obj = await MatchRepository.get_players(m)
        assert {p.user.username for p in by_obj} == {"alice", "bob"}
        by_id = await MatchRepository.get_players(m.id)
        assert {p.user.username for p in by_id} == {"alice", "bob"}

    async def test_remove_player(self, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        u = await make_user(1, "alice")
        await MatchRepository.add_player(m, u)
        await MatchRepository.remove_player(m, u)
        assert await MatchRepository.get_players(m) == []

    async def test_remove_player_absent_is_noop(self, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        u = await make_user(1, "alice")
        # Not a player — must not raise.
        await MatchRepository.remove_player(m, u)
        assert await MatchRepository.get_players(m) == []

    async def test_get_all_for_schedule_ordered(self, db):
        t = await Tournament.create(name="T")
        late = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 5, 12))
        early = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        result = await MatchRepository.get_all_for_schedule()
        assert [m.id for m in result] == [early.id, late.id]

    async def test_get_for_date_default_filters(self, db):
        t = await Tournament.create(name="T")
        sr = await StreamRoom.create(name="Room 1")
        target = date(2025, 3, 10)
        keep = await Match.create(tournament=t, scheduled_at=utc(2025, 3, 10, 15), stream_room=sr)
        # finished -> excluded by default
        await Match.create(
            tournament=t, scheduled_at=utc(2025, 3, 10, 16), stream_room=sr, finished_at=utc(2025, 3, 10, 18)
        )
        # no stream room -> excluded by default
        await Match.create(tournament=t, scheduled_at=utc(2025, 3, 10, 17))
        # different day -> excluded
        await Match.create(tournament=t, scheduled_at=utc(2025, 3, 11, 15), stream_room=sr)
        result = await MatchRepository.get_for_date(target)
        assert [m.id for m in result] == [keep.id]

    async def test_get_for_date_include_finished_and_no_stream_room(self, db):
        t = await Tournament.create(name="T")
        sr = await StreamRoom.create(name="Room 1")
        target = date(2025, 3, 10)
        with_room = await Match.create(tournament=t, scheduled_at=utc(2025, 3, 10, 15), stream_room=sr)
        finished = await Match.create(
            tournament=t, scheduled_at=utc(2025, 3, 10, 16), stream_room=sr, finished_at=utc(2025, 3, 10, 18)
        )
        no_room = await Match.create(tournament=t, scheduled_at=utc(2025, 3, 10, 17))
        result = await MatchRepository.get_for_date(target, exclude_finished=False, require_stream_room=False)
        assert {m.id for m in result} == {with_room.id, finished.id, no_room.id}

    async def test_get_for_player(self, db):
        t = await Tournament.create(name="T")
        u = await make_user(222, "alice")
        m1 = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 1, 12))
        await Match.create(tournament=t, scheduled_at=utc(2025, 1, 2, 12))
        await MatchRepository.add_player(m1, u)
        result = await MatchRepository.get_for_player(222)
        assert [m.id for m in result] == [m1.id]
