"""Coverage for standalone utility modules.

These are all pure helpers — no DB, no Discord connection, no network. Env-var
helpers are exercised by monkeypatching ``os.environ`` (they read lazily on each
call), message builders by asserting the exact formatted strings, and the QR
helper by decoding the PNG/data-URI it produces.
"""

import base64

import pytest

from application.utils import discord_messages as dm
from application.utils import easter_eggs, environment, qrcode_util


# ---------------------------------------------------------------------------
# environment.py
# ---------------------------------------------------------------------------

class TestGetEnvironment:
    def test_default_is_development(self, monkeypatch):
        monkeypatch.delenv('ENVIRONMENT', raising=False)
        assert environment.get_environment() == 'development'

    def test_normalizes_case_and_whitespace(self, monkeypatch):
        monkeypatch.setenv('ENVIRONMENT', '  Production  ')
        assert environment.get_environment() == 'production'

    def test_is_production_true(self, monkeypatch):
        monkeypatch.setenv('ENVIRONMENT', 'PRODUCTION')
        assert environment.is_production() is True

    def test_is_production_false_for_development(self, monkeypatch):
        monkeypatch.setenv('ENVIRONMENT', 'development')
        assert environment.is_production() is False


class TestGetBaseUrl:
    def test_default(self, monkeypatch):
        monkeypatch.delenv('BASE_URL', raising=False)
        assert environment.get_base_url() == 'http://localhost:8000'

    def test_strips_trailing_slashes(self, monkeypatch):
        monkeypatch.setenv('BASE_URL', 'https://example.com/')
        assert environment.get_base_url() == 'https://example.com'

    def test_custom_no_trailing_slash_unchanged(self, monkeypatch):
        monkeypatch.setenv('BASE_URL', 'https://sgl.example.org')
        assert environment.get_base_url() == 'https://sgl.example.org'


class TestTelemetryEnabled:
    def test_unset_defaults_to_enabled(self, monkeypatch):
        monkeypatch.delenv('TELEMETRY_ENABLED', raising=False)
        assert environment.telemetry_enabled() is True

    @pytest.mark.parametrize('value', ['1', 'true', 'YES', 'On', ' true '])
    def test_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv('TELEMETRY_ENABLED', value)
        assert environment.telemetry_enabled() is True

    @pytest.mark.parametrize('value', ['0', 'false', 'no', 'off', '', 'nonsense'])
    def test_falsey_values(self, monkeypatch, value):
        monkeypatch.setenv('TELEMETRY_ENABLED', value)
        assert environment.telemetry_enabled() is False


class TestValidateSecurityConfig:
    def test_missing_storage_secret_raises(self, monkeypatch):
        monkeypatch.delenv('STORAGE_SECRET', raising=False)
        monkeypatch.setenv('ENVIRONMENT', 'development')
        with pytest.raises(RuntimeError, match='STORAGE_SECRET is required'):
            environment.validate_security_config()

    def test_blank_storage_secret_raises(self, monkeypatch):
        monkeypatch.setenv('STORAGE_SECRET', '   ')
        monkeypatch.setenv('ENVIRONMENT', 'development')
        with pytest.raises(RuntimeError, match='STORAGE_SECRET is required'):
            environment.validate_security_config()

    def test_development_short_secret_ok(self, monkeypatch):
        """Outside production a short secret is accepted (no length/DB checks)."""
        monkeypatch.setenv('STORAGE_SECRET', 'short')
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.delenv('DB_USERNAME', raising=False)
        monkeypatch.delenv('DB_PASSWORD', raising=False)
        assert environment.validate_security_config() is None

    def test_production_short_secret_raises(self, monkeypatch):
        monkeypatch.setenv('STORAGE_SECRET', 'a' * 31)
        monkeypatch.setenv('ENVIRONMENT', 'production')
        with pytest.raises(RuntimeError, match='at least 32 characters'):
            environment.validate_security_config()

    def test_production_missing_db_username_raises(self, monkeypatch):
        monkeypatch.setenv('STORAGE_SECRET', 'a' * 32)
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.delenv('DB_USERNAME', raising=False)
        monkeypatch.setenv('DB_PASSWORD', 'pw')
        with pytest.raises(RuntimeError, match='DB_USERNAME must be set'):
            environment.validate_security_config()

    def test_production_blank_db_username_raises(self, monkeypatch):
        monkeypatch.setenv('STORAGE_SECRET', 'a' * 32)
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('DB_USERNAME', '   ')
        monkeypatch.setenv('DB_PASSWORD', 'pw')
        with pytest.raises(RuntimeError, match='DB_USERNAME must be set'):
            environment.validate_security_config()

    def test_production_missing_db_password_raises(self, monkeypatch):
        monkeypatch.setenv('STORAGE_SECRET', 'a' * 32)
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('DB_USERNAME', 'sgl')
        monkeypatch.delenv('DB_PASSWORD', raising=False)
        with pytest.raises(RuntimeError, match='DB_PASSWORD must be set'):
            environment.validate_security_config()

    def test_production_all_present_ok(self, monkeypatch):
        monkeypatch.setenv('STORAGE_SECRET', 'a' * 40)
        monkeypatch.setenv('ENVIRONMENT', 'production')
        monkeypatch.setenv('DB_USERNAME', 'sgl')
        monkeypatch.setenv('DB_PASSWORD', 'secret')
        assert environment.validate_security_config() is None


# ---------------------------------------------------------------------------
# discord_messages.py
# ---------------------------------------------------------------------------

class TestPlayersLabel:
    def test_empty(self):
        assert dm._players_label(None) == ''
        assert dm._players_label([]) == ''

    def test_two_players_uses_vs(self):
        assert dm._players_label(['Alice', 'Bob']) == 'Alice vs Bob'

    def test_three_players_comma_joined(self):
        assert dm._players_label(['A', 'B', 'C']) == 'A, B, C'

    def test_one_player(self):
        assert dm._players_label(['Solo']) == 'Solo'


class TestMatchInfoLines:
    def test_all_fields(self):
        lines = dm._match_info_lines(
            player_names=['A', 'B'],
            scheduled_at_display='2025-01-01 10:00 EST',
            stream_room_name='Main Stage',
        )
        assert lines == [
            'Players: A vs B',
            'Scheduled for: 2025-01-01 10:00 EST',
            'Stage: Main Stage',
        ]

    def test_empty_data_omits_lines(self):
        assert dm._match_info_lines() == []

    def test_custom_time_label(self):
        lines = dm._match_info_lines(scheduled_at_display='soon', time_label='New time')
        assert lines == ['New time: soon']


class TestSchedulingDms:
    def test_scheduled_dm_contains_tournament_and_body(self):
        msg = dm.scheduled_dm(
            'Cool Cup', '2025-03-01 12:00 EST',
            player_names=['A', 'B'], stream_room_name='Stage 1',
        )
        assert '**Cool Cup**' in msg
        assert 'Players: A vs B' in msg
        assert 'Scheduled for: 2025-03-01 12:00 EST' in msg
        assert 'Stage: Stage 1' in msg
        assert msg.endswith('Good luck!')

    def test_rescheduled_dm_uses_new_time_label(self):
        msg = dm.rescheduled_dm('Cool Cup', '2025-03-02 12:00 EST', player_names=['A', 'B'])
        assert 'has been rescheduled' in msg
        assert 'New time: 2025-03-02 12:00 EST' in msg
        assert msg.endswith('Please update your calendar.')


class TestAcknowledgmentRequestDm:
    def test_rescheduled_branch(self):
        msg = dm.acknowledgment_request_dm(
            'Cup', 'later', rescheduled=True,
            stream_room_name='Stage', player_names=['A', 'B'],
        )
        assert 'has been rescheduled' in msg
        assert 'New time: later' in msg
        assert 'Stage: Stage' in msg
        assert 'Acknowledge' in msg

    def test_not_rescheduled_branch(self):
        msg = dm.acknowledgment_request_dm('Cup', 'noon', rescheduled=False)
        assert 'A match has been scheduled for you' in msg
        assert 'Scheduled for: noon' in msg
        assert msg.endswith("Click **Acknowledge** below to confirm you've seen this.")


class TestCheckedInAndStateChangedDms:
    def test_checked_in_with_info(self):
        msg = dm.checked_in_dm('Cup', player_names=['A', 'B'], scheduled_at_display='noon')
        assert 'has been checked in' in msg
        assert 'Players: A vs B' in msg
        assert msg.endswith('about to begin — good luck!')

    def test_checked_in_without_info_has_no_block(self):
        msg = dm.checked_in_dm('Cup')
        assert 'has been checked in' in msg
        # No players/time/stage block when nothing supplied.
        assert 'Players:' not in msg

    def test_state_changed_with_info_appends_block(self):
        msg = dm.state_changed_dm('Cup', 'IN_PROGRESS', player_names=['A', 'B'])
        assert '**IN_PROGRESS**' in msg
        assert 'Players: A vs B' in msg

    def test_state_changed_without_info(self):
        msg = dm.state_changed_dm('Cup', 'DONE')
        assert msg == 'Your match in **Cup** is now: **DONE**.'


class TestStreamCandidateAndSeedDms:
    def test_stream_candidate_dm(self):
        msg = dm.stream_candidate_dm('Cup', 'noon', player_names=['A', 'B'])
        assert 'potential stream match' in msg
        assert 'Players: A vs B' in msg
        assert msg.endswith('Use the buttons below to sign up as crew.')

    def test_seed_dm_with_info(self):
        msg = dm.seed_dm(
            'Alice', 'Cup', 'https://seed.example/abc',
            player_names=['Alice', 'Bob'], scheduled_at_display='noon',
        )
        assert msg.startswith('Hello Alice,')
        assert 'https://seed.example/abc' in msg
        assert 'Players: Alice vs Bob' in msg
        assert msg.endswith('Good luck and have fun!')

    def test_seed_dm_without_info_omits_block(self):
        msg = dm.seed_dm('Alice', 'Cup', 'https://seed.example/abc')
        assert 'Players:' not in msg
        assert 'https://seed.example/abc' in msg


class TestCrewAssignmentDm:
    def test_all_fields(self):
        msg = dm.crew_assignment_dm(
            'Commentator', 'Grand Final', 'noon', 'Stage 2', ['A', 'B'],
        )
        assert "You've been approved as Commentator." in msg
        assert '**Match:** Grand Final' in msg
        assert '**Players:** A vs B' in msg
        assert '**Scheduled:** noon' in msg
        assert '**Stage:** Stage 2' in msg
        assert msg.endswith('Please click below to acknowledge your assignment.')

    def test_optional_fields_suppressed(self):
        msg = dm.crew_assignment_dm('Tracker', None, '', None, None)
        assert "You've been approved as Tracker." in msg
        assert '**Match:**' not in msg
        assert '**Players:**' not in msg
        assert '**Scheduled:**' not in msg
        assert '**Stage:**' not in msg


class TestVolunteerDms:
    def test_shift_lines_with_label(self):
        lines = dm._volunteer_shift_lines('Runner', 'Booth A', 'start', 'end')
        assert lines[0] == '**Position:** Runner — Booth A'
        assert '**Start:** start' in lines
        assert '**End:** end' in lines

    def test_shift_lines_without_label(self):
        lines = dm._volunteer_shift_lines('Runner', None, '', '')
        assert lines == ['**Position:** Runner']

    def test_assignment_dm(self):
        msg = dm.volunteer_assignment_dm('Runner', 'Booth A', 'start', 'end')
        assert msg.startswith("You've been scheduled for a volunteer shift")
        assert '**Position:** Runner — Booth A' in msg
        assert msg.endswith('Please click below to acknowledge your shift.')

    def test_reminder_dm(self):
        msg = dm.volunteer_reminder_dm('Runner', None, 'start', 'end')
        assert msg.startswith('⏰ Reminder')
        assert '**Position:** Runner' in msg

    def test_ack_confirmation(self):
        assert dm.volunteer_ack_confirmation('Runner') == \
            'Thanks! Your **Runner** shift is acknowledged.'


class TestEphemeralReplies:
    def test_match_ack_with_players(self):
        assert dm.match_ack_confirmation('A vs B') == \
            'You have acknowledged your match (A vs B). Thanks!'

    def test_match_ack_without_players(self):
        assert dm.match_ack_confirmation('') == 'You have acknowledged your match. Thanks!'

    def test_crew_ack_with_players(self):
        msg = dm.crew_ack_confirmation('Commentator', 'A vs B')
        assert msg == 'You have acknowledged your Commentator assignment (A vs B). Thanks!'

    def test_crew_ack_without_players(self):
        msg = dm.crew_ack_confirmation('Commentator', '')
        assert msg == 'You have acknowledged your Commentator assignment. Thanks!'

    def test_crew_signup_with_players(self):
        msg = dm.crew_signup_confirmation('Tracker', 'A vs B')
        assert msg == (
            'You have been signed up as a **Tracker** for the match (A vs B). '
            'Awaiting admin approval.'
        )

    def test_crew_signup_without_players(self):
        msg = dm.crew_signup_confirmation('Tracker', '')
        assert msg == 'You have been signed up as a **Tracker**. Awaiting admin approval.'

    def test_unwatch_was_watching(self):
        assert dm.unwatch_confirmation('A vs B', True) == \
            'You are no longer watching the match (A vs B).'

    def test_unwatch_was_not_watching(self):
        assert dm.unwatch_confirmation('A vs B', False) == \
            'You were not watching the match (A vs B).'

    def test_unwatch_without_players(self):
        assert dm.unwatch_confirmation('', True) == 'You are no longer watching the match.'


# ---------------------------------------------------------------------------
# easter_eggs.py
# ---------------------------------------------------------------------------

class TestEasterEggs:
    def _all_facts(self):
        return (
            easter_eggs.COASTER_FACTS + easter_eggs.CAT_FACTS + easter_eggs.BALATRO_FACTS
            + easter_eggs.DIABLO_FACTS + easter_eggs.WOW_FACTS + easter_eggs.HAMILTON_FACTS
            + easter_eggs.CLOVERPIT_TIPS
        )

    def test_random_fact_returns_known_string(self):
        fact = easter_eggs.random_fact()
        assert isinstance(fact, str) and fact
        assert fact in self._all_facts()

    def test_random_cat_fact_from_cat_pool(self):
        fact = easter_eggs.random_cat_fact()
        assert fact in easter_eggs.CAT_FACTS

    def test_random_fact_deterministic_with_seed(self):
        import random
        state = random.getstate()
        try:
            random.seed(1234)
            first = easter_eggs.random_fact()
            random.seed(1234)
            second = easter_eggs.random_fact()
            assert first == second
        finally:
            random.setstate(state)


# ---------------------------------------------------------------------------
# qrcode_util.py
# ---------------------------------------------------------------------------

class TestQrCodeUtil:
    def test_png_bytes_have_png_signature(self):
        # The util now takes the fully-built (tenant-qualified) URL directly.
        data = qrcode_util.asset_qr_png_bytes('https://sgl.example.org/t/acme/equipment/7')
        assert isinstance(data, bytes) and len(data) > 0
        assert data[:8] == b'\x89PNG\r\n\x1a\n'

    def test_data_uri_prefix_and_decodes_to_png(self):
        url = 'https://sgl.example.org/t/acme/equipment/7'
        uri = qrcode_util.asset_qr_data_uri(url)
        prefix = 'data:image/png;base64,'
        assert uri.startswith(prefix)
        decoded = base64.b64decode(uri[len(prefix):])
        assert decoded[:8] == b'\x89PNG\r\n\x1a\n'
        assert decoded == qrcode_util.asset_qr_png_bytes(url)
