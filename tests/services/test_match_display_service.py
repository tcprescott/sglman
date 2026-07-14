from datetime import datetime
from types import SimpleNamespace

import pytest

from application.services.match_display_service import MatchDisplayService
from application.utils.timezone import format_eastern_datetime


@pytest.fixture
def display_service():
    # _get_match_state / _format_match_for_display are pure formatting helpers
    # (no repository access), so a plain instance is sufficient.
    return MatchDisplayService()


def make_match(**overrides):
    defaults = dict(
        id=1,
        tournament_id=1,
        seated_at=None,
        started_at=None,
        finished_at=None,
        confirmed_at=None,
        created_at=datetime(2025, 1, 1, 12, 0),
        scheduled_at=datetime(2025, 1, 15, 19, 30),
        comment=None,
        tournament=SimpleNamespace(name="Test Tournament", seed_generator=None, is_racetime_enabled=False),
        stream_room=None,
        stream_room_id=None,
        generated_seed=None,
        is_stream_candidate=False,
        players=[],
        commentators=[],
        trackers=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# _get_match_state
# ---------------------------------------------------------------------------


class TestGetMatchState:
    def test_scheduled_when_no_timestamps(self, display_service):
        assert display_service._get_match_state(make_match()) == "Scheduled"

    def test_checked_in_when_only_seated(self, display_service):
        match = make_match(seated_at=datetime.now())
        assert display_service._get_match_state(match) == "Checked In"

    def test_started_when_seated_and_started(self, display_service):
        now = datetime.now()
        match = make_match(seated_at=now, started_at=now)
        assert display_service._get_match_state(match) == "Started"

    def test_finished_when_finished_set(self, display_service):
        now = datetime.now()
        match = make_match(seated_at=now, started_at=now, finished_at=now)
        assert display_service._get_match_state(match) == "Finished"

    def test_confirmed_takes_highest_priority(self, display_service):
        now = datetime.now()
        match = make_match(seated_at=now, started_at=now, finished_at=now, confirmed_at=now)
        assert display_service._get_match_state(match) == "Confirmed"

    def test_confirmed_beats_finished(self, display_service):
        now = datetime.now()
        # Even without started_at, confirmed_at should dominate
        match = make_match(finished_at=now, confirmed_at=now)
        assert display_service._get_match_state(match) == "Confirmed"


# ---------------------------------------------------------------------------
# _format_match_for_display
# ---------------------------------------------------------------------------


class TestFormatMatchForDisplay:
    def test_returns_id(self, display_service):
        result = display_service._format_match_for_display(make_match(id=77))
        assert result["id"] == 77

    def test_state_is_scheduled_by_default(self, display_service):
        result = display_service._format_match_for_display(make_match())
        assert result["state"] == "Scheduled"

    def test_state_timestamp_falls_back_to_created_at_when_scheduled(self, display_service):
        result = display_service._format_match_for_display(make_match())
        assert result["state_timestamp"] == format_eastern_datetime(
            datetime(2025, 1, 1, 12, 0)
        )

    def test_stream_room_empty_when_none(self, display_service):
        result = display_service._format_match_for_display(make_match(stream_room=None))
        assert result["stream_room"] == ""

    def test_stream_room_name_when_set(self, display_service):
        match = make_match(stream_room=SimpleNamespace(name="Stage 1", stream_url="https://twitch.tv/sglive1"))
        result = display_service._format_match_for_display(match)
        assert result["stream_room"] == "Stage 1"
        assert result["stream_room_url"] == "https://twitch.tv/sglive1"

    def test_stream_room_url_empty_when_none(self, display_service):
        result = display_service._format_match_for_display(make_match(stream_room=None))
        assert result["stream_room_url"] == ""

    def test_stream_room_url_empty_for_invalid_scheme(self, display_service):
        match = make_match(stream_room=SimpleNamespace(name="Stage 1", stream_url="javascript:alert(1)"))
        result = display_service._format_match_for_display(match)
        assert result["stream_room_url"] == ""

    def test_seed_empty_when_none(self, display_service):
        result = display_service._format_match_for_display(make_match(generated_seed=None))
        assert result["seed"] == ""

    def test_seed_url_when_set(self, display_service):
        match = make_match(generated_seed=SimpleNamespace(seed_url="https://alttpr.com/h/abc"))
        result = display_service._format_match_for_display(match)
        assert result["seed"] == "https://alttpr.com/h/abc"

    def test_tournament_name_in_result(self, display_service):
        result = display_service._format_match_for_display(make_match())
        assert result["tournament"] == "Test Tournament"

    def test_tournament_empty_when_none(self, display_service):
        match = make_match(tournament=None)
        result = display_service._format_match_for_display(match)
        assert result["tournament"] == ""

    def test_players_formatted_as_dicts(self, display_service):
        player = SimpleNamespace(
            user=SimpleNamespace(preferred_name="Alice", discord_id="111"),
            finish_rank=1,
            assigned_station="A",
        )
        result = display_service._format_match_for_display(make_match(players=[player]))
        assert result["players"] == [
            {"name": "Alice", "finish_rank": 1, "station": "A", "discord_id": "111"}
        ]

    def test_multiple_players_all_included(self, display_service):
        players = [
            SimpleNamespace(user=SimpleNamespace(preferred_name="Alice", discord_id="111"), finish_rank=1, assigned_station="A"),
            SimpleNamespace(user=SimpleNamespace(preferred_name="Bob", discord_id="222"), finish_rank=2, assigned_station="B"),
        ]
        result = display_service._format_match_for_display(make_match(players=players))
        assert len(result["players"]) == 2

    def test_commentators_formatted_as_dicts(self, display_service):
        commentator = SimpleNamespace(
            id=11,
            user=SimpleNamespace(preferred_name="Charlie", discord_id="123"),
            approved=True,
            acknowledged_at=None,
            auto_acknowledged=False,
        )
        result = display_service._format_match_for_display(make_match(commentators=[commentator]))
        assert result["commentators"] == [
            {
                "name": "Charlie",
                "approved": True,
                "discord_id": "123",
                "acknowledged": False,
                "ack_ts": "",
                "id": 11,
            }
        ]

    def test_trackers_formatted_as_dicts(self, display_service):
        tracker = SimpleNamespace(
            id=22,
            user=SimpleNamespace(preferred_name="Dana", discord_id="456"),
            approved=False,
            acknowledged_at=None,
            auto_acknowledged=False,
        )
        result = display_service._format_match_for_display(make_match(trackers=[tracker]))
        assert result["trackers"] == [
            {
                "name": "Dana",
                "approved": False,
                "discord_id": "456",
                "acknowledged": False,
                "ack_ts": "",
                "id": 22,
            }
        ]

    def test_state_timestamp_set_when_seated(self, display_service):
        match = make_match(seated_at=datetime(2025, 1, 15, 19, 30))
        result = display_service._format_match_for_display(match)
        assert result["state_timestamp"] is not None

    def test_state_timestamp_reflects_highest_state(self, display_service):
        now = datetime.now()
        match = make_match(seated_at=now, started_at=now, finished_at=now, confirmed_at=now)
        result = display_service._format_match_for_display(match)
        assert result["state"] == "Confirmed"
        assert result["state_timestamp"] is not None

    def test_scheduled_at_formatted_as_string(self, display_service):
        match = make_match(scheduled_at=datetime(2025, 1, 15, 19, 30))
        result = display_service._format_match_for_display(match)
        assert isinstance(result["scheduled_at"], str)
        assert result["scheduled_at"] != ""

    def test_scheduled_at_empty_when_none(self, display_service):
        match = make_match(scheduled_at=None)
        result = display_service._format_match_for_display(match)
        assert result["scheduled_at"] == ""


# ---------------------------------------------------------------------------
# _format_match_for_display — is_stream_candidate field
# ---------------------------------------------------------------------------


class TestFormatMatchIsStreamCandidate:
    def test_is_stream_candidate_false_by_default(self, display_service):
        result = display_service._format_match_for_display(make_match())
        assert result["is_stream_candidate"] is False

    def test_is_stream_candidate_true_when_set(self, display_service):
        result = display_service._format_match_for_display(make_match(is_stream_candidate=True))
        assert result["is_stream_candidate"] is True


class TestFormatMatchIsRacetime:
    def test_is_racetime_false_for_on_site_tournament(self, display_service):
        result = display_service._format_match_for_display(make_match())
        assert result["is_racetime"] is False

    def test_is_racetime_true_when_tournament_racetime_enabled(self, display_service):
        match = make_match(
            tournament=SimpleNamespace(
                name="Online Cup", seed_generator=None, is_racetime_enabled=True
            )
        )
        result = display_service._format_match_for_display(match)
        assert result["is_racetime"] is True
