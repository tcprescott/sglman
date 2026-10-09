"""A URL someone typed is only ever stored, and only ever drawn, as http(s).

These fields land in an ``<a href>``, where ``javascript:`` runs in the clicker's
session on the shared platform origin. The VoD link is the sharpest case: any
member submits it and qualifier staff click it in the review queue.
"""

from datetime import datetime, timedelta, timezone

import pytest

from application.services import StageService, TournamentService
from application.services.async_qualifier.async_qualifier_service import AsyncQualifierService
from application.utils.safe_url import http_url_or_empty, normalize_http_url
from application.utils.ssrf import ensure_public_host
from models import AsyncQualifierRun, Role, User, UserRole

BAD_URLS = ['javascript:alert(1)', ' JavaScript:alert(1)', 'data:text/html,<script>1</script>', 'vbscript:x', '//evil.example']


class TestHelpers:
    @pytest.mark.parametrize('raw', BAD_URLS)
    def test_non_http_is_refused_and_not_drawn(self, raw):
        with pytest.raises(ValueError, match='http'):
            normalize_http_url(raw, 'The link')
        assert http_url_or_empty(raw) == ''

    def test_blank_clears_and_http_passes_through(self):
        assert normalize_http_url('  ', 'The link') is None
        assert normalize_http_url(' https://twitch.tv/x ', 'The link') == 'https://twitch.tv/x'
        assert http_url_or_empty('HTTP://example.com') == 'HTTP://example.com'


async def _staff() -> User:
    user = await User.create(discord_id=880001, username='staff')
    await UserRole.create(user=user, role=Role.STAFF)
    return user


class TestStoredFields:
    async def test_stage_stream_url(self, db):
        staff = await _staff()
        service = StageService()
        with pytest.raises(ValueError):
            await service.create_stage('Main', stream_url='javascript:alert(1)', actor=staff)
        stage = await service.create_stage('Main', stream_url='https://twitch.tv/main', actor=staff)
        with pytest.raises(ValueError):
            await service.update_stage(stage, stream_url='javascript:alert(1)', actor=staff)

    @pytest.mark.parametrize('field', ['rules_url', 'bracket_url'])
    async def test_tournament_links(self, db, field):
        staff = await _staff()
        service = TournamentService()
        with pytest.raises(ValueError):
            await service.create_tournament(name='Cup', actor=staff, **{field: 'javascript:alert(1)'})
        t = await service.create_tournament(name='Cup', actor=staff, **{field: 'https://example.com/r'})
        with pytest.raises(ValueError):
            await service.update_tournament(t, actor=staff, **{field: 'javascript:alert(1)'})

    async def test_qualifier_vod_url(self, db):
        staff = await _staff()
        player = await User.create(discord_id=880002, username='runner')
        service = AsyncQualifierService()
        now = datetime.now(timezone.utc)
        q = await service.create_qualifier(
            staff, name='Q', opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=1),
            runs_per_pool=1, allowed_reattempts=1,
        )
        pool = await service.create_pool(staff, q.id, name='A')
        await service.add_permalink(staff, pool.id, url='https://x/seed')
        run = await service.start_run(player, q.id, pool.id)
        await AsyncQualifierRun.filter(id=run.id).update(started_at=now - timedelta(hours=2))
        with pytest.raises(ValueError, match='VoD'):
            await service.submit_run(player, run.id, elapsed_seconds=3600, runner_vod_url='javascript:alert(1)')
        submitted = await service.submit_run(
            player, run.id, elapsed_seconds=3600, runner_vod_url='https://youtu.be/x',
        )
        assert submitted.runner_vod_url == 'https://youtu.be/x'


class TestSsrfGuard:
    async def test_carrier_grade_nat_range_is_refused(self, monkeypatch):
        import socket
        monkeypatch.setattr(
            socket, 'getaddrinfo', lambda *a, **k: [(None, None, None, None, ('100.64.1.1', 0))],
        )
        with pytest.raises(ValueError, match='public address'):
            await ensure_public_host('internal.example')
