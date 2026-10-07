"""Tests for the Sentry wiring in ``application/utils/sentry.py``.

Covers what ``init_sentry`` decides from the environment and what every event
picks up on the way out: the tenant in scope, the signed-in user when the
request scope is gone, and scoped tags that never outlive their block.
"""

import logging

import sentry_sdk

from application.tenant_context import tenant_scope
from application.utils import sentry as wiring


class TestEnrichment:
    def test_tags_tenant_in_scope(self):
        with tenant_scope(42):
            event = wiring._before_send({'tags': {'worker': 'x'}}, None)
        assert event['tags'] == {'worker': 'x', 'tenant_id': '42'}

    def test_no_tenant_no_tag(self):
        with tenant_scope(None):
            event = wiring._before_send({}, None)
        assert 'tenant_id' not in (event.get('tags') or {})

    def test_existing_user_is_kept(self, monkeypatch):
        monkeypatch.setattr(wiring, '_session_user', lambda: {'id': '9'})
        event = wiring._before_send({'user': {'id': '1'}}, None)
        assert event['user'] == {'id': '1'}

    def test_session_user_fills_a_missing_user(self, monkeypatch):
        monkeypatch.setattr(wiring, '_session_user', lambda: {'id': '9', 'username': 'u'})
        event = wiring._before_send({}, None)
        assert event['user'] == {'id': '9', 'username': 'u'}

    def test_session_user_is_none_outside_a_client(self):
        assert wiring._session_user() is None

    def test_still_scrubs_auth_headers(self):
        event = wiring._before_send(
            {'request': {'headers': {'Authorization': 'Bearer x'}, 'cookies': {'a': 'b'}}}, None,
        )
        assert event['request']['headers']['Authorization'] == '[Filtered]'
        assert 'cookies' not in event['request']

    def test_log_gets_tenant_attribute(self):
        with tenant_scope(7):
            log = wiring._before_send_log({'attributes': {}}, None)
        assert log['attributes']['tenant_id'] == 7


class TestConfig:
    def test_release_prefers_explicit(self, monkeypatch):
        monkeypatch.setenv('SENTRY_RELEASE', 'custom-1')
        monkeypatch.setenv('GIT_SHA', 'abcdef1234567890')
        assert wiring._release() == 'custom-1'

    def test_release_from_git_sha(self, monkeypatch):
        monkeypatch.delenv('SENTRY_RELEASE', raising=False)
        monkeypatch.setenv('GIT_SHA', 'abcdef1234567890')
        assert wiring._release() == 'wizzrobe@abcdef123456'

    def test_release_unset(self, monkeypatch):
        monkeypatch.delenv('SENTRY_RELEASE', raising=False)
        monkeypatch.delenv('GIT_SHA', raising=False)
        assert wiring._release() is None

    def test_traces_default_on_in_production_only(self, monkeypatch):
        monkeypatch.delenv('SENTRY_TRACES_SAMPLE_RATE', raising=False)
        monkeypatch.setattr(wiring, 'is_production', lambda: True)
        assert wiring._traces_sample_rate() == 0.1
        monkeypatch.setattr(wiring, 'is_production', lambda: False)
        assert wiring._traces_sample_rate() == 0.0

    def test_traces_env_wins_and_is_clamped(self, monkeypatch):
        monkeypatch.setattr(wiring, 'is_production', lambda: True)
        monkeypatch.setenv('SENTRY_TRACES_SAMPLE_RATE', '0')
        assert wiring._traces_sample_rate() == 0.0
        monkeypatch.setenv('SENTRY_TRACES_SAMPLE_RATE', '7')
        assert wiring._traces_sample_rate() == 1.0
        monkeypatch.setenv('SENTRY_TRACES_SAMPLE_RATE', 'lots')
        assert wiring._traces_sample_rate() == 0.0

    def test_logs_level(self, monkeypatch):
        monkeypatch.delenv('SENTRY_LOGS_LEVEL', raising=False)
        assert wiring._sentry_logs_level() == logging.INFO
        monkeypatch.setenv('SENTRY_LOGS_LEVEL', 'warning')
        assert wiring._sentry_logs_level() == logging.WARNING
        monkeypatch.setenv('SENTRY_LOGS_LEVEL', 'off')
        assert wiring._sentry_logs_level() is None


class TestScopedTags:
    def test_tags_live_only_inside_the_block(self):
        with wiring.sentry_tags(worker='seed roll', skipped=None):
            tags = sentry_sdk.get_current_scope()._tags
            assert tags['worker'] == 'seed roll'
            assert 'skipped' not in tags
            wiring.tag_current_scope(tenant_id=3)
            assert sentry_sdk.get_current_scope()._tags['tenant_id'] == '3'
        outside = sentry_sdk.get_current_scope()._tags
        assert 'worker' not in outside and 'tenant_id' not in outside
