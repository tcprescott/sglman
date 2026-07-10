"""Tests for TelemetryService: capture paths, aggregations, and Staff gating.

Exercises the real aggregation SQL (GROUP BY / COUNT DISTINCT) against the
in-memory SQLite ``db`` fixture, plus the best-effort capture guarantees and
the Staff-only read boundary.
"""

import json

import pytest

from application.events import Event, EventType
from application.repositories.telemetry_repository import TelemetryRepository
from application.services.telemetry_service import (
    TelemetryCategory,
    TelemetryEventType,
    TelemetryService,
)
from models import Role, TelemetryEvent, User, UserRole


async def _staff(discord_id: int = 1001, username: str = 'staff') -> User:
    user = await User.create(discord_id=discord_id, username=username)
    await UserRole.create(user=user, role=Role.STAFF)
    return user


async def _plain(discord_id: int = 2002, username: str = 'nobody') -> User:
    return await User.create(discord_id=discord_id, username=username)


# ---------------------------------------------------------------------------
# record_event — event-bus mirror
# ---------------------------------------------------------------------------


class TestRecordEvent:
    async def test_mirrors_domain_event_with_actor(self, db):
        actor = await _plain()
        await TelemetryService().record_event(
            Event.create(EventType.MATCH_CREATED, {'match_id': 5}, actor)
        )
        rows = await TelemetryEvent.all()
        assert len(rows) == 1
        row = rows[0]
        assert row.category == TelemetryCategory.DOMAIN
        assert row.event_type == EventType.MATCH_CREATED
        assert row.user_id == actor.id
        assert row.path is None
        details = json.loads(row.details)
        assert details['match_id'] == 5
        assert details['actor_username'] == 'nobody'

    async def test_system_event_without_actor(self, db):
        await TelemetryService().record_event(
            Event.create(EventType.MATCH_STARTED, {'match_id': 9})
        )
        row = (await TelemetryEvent.all())[0]
        assert row.user_id is None
        assert row.event_type == EventType.MATCH_STARTED

    async def test_disabled_is_noop(self, db, monkeypatch):
        monkeypatch.setenv('TELEMETRY_ENABLED', 'false')
        await TelemetryService().record_event(Event.create(EventType.MATCH_CREATED, {}))
        assert await TelemetryEvent.all().count() == 0


# ---------------------------------------------------------------------------
# track_page_view / track_interaction — engagement capture
# ---------------------------------------------------------------------------


class TestTrackPageView:
    async def test_resolves_user_and_records(self, db):
        user = await _plain(discord_id=555, username='viewer')
        await TelemetryService().track_page_view(
            path='/admin', discord_id='555', username='viewer',
            session_id='sess-1', params={'tab': 'Reports'},
        )
        row = (await TelemetryEvent.all())[0]
        assert row.category == TelemetryCategory.PAGE
        assert row.event_type == TelemetryEventType.PAGE_VIEW
        assert row.user_id == user.id
        assert row.path == '/admin'
        assert row.session_id == 'sess-1'
        details = json.loads(row.details)
        assert details['tab'] == 'Reports'
        assert details['actor_username'] == 'viewer'

    async def test_unknown_discord_id_records_anonymous(self, db):
        await TelemetryService().track_page_view(path='/home', discord_id='999999')
        row = (await TelemetryEvent.all())[0]
        assert row.user_id is None
        assert row.path == '/home'

    async def test_disabled_is_noop(self, db, monkeypatch):
        monkeypatch.setenv('TELEMETRY_ENABLED', '0')
        await TelemetryService().track_page_view(path='/home')
        assert await TelemetryEvent.all().count() == 0


class TestTrackInteraction:
    async def test_records_interaction(self, db):
        user = await _plain(discord_id=777, username='clicker')
        await TelemetryService().track_interaction(
            event_type=TelemetryEventType.REPORT_VIEWED, path='audit',
            discord_id='777', session_id='s9',
        )
        row = (await TelemetryEvent.all())[0]
        assert row.category == TelemetryCategory.INTERACTION
        assert row.event_type == 'report.viewed'
        assert row.path == 'audit'
        assert row.user_id == user.id
        assert row.session_id == 's9'


# ---------------------------------------------------------------------------
# Aggregations (run the real GROUP BY / COUNT DISTINCT on SQLite)
# ---------------------------------------------------------------------------


class TestAggregations:
    async def test_top_paths_counts_views_and_distinct_users(self, db):
        staff = await _staff()
        u1 = await _plain(3001, 'a')
        u2 = await _plain(3002, 'b')
        for uid in (u1.id, u1.id, u2.id):
            await TelemetryRepository.create(
                category='page', event_type='page.view', path='/admin', user_id=uid,
            )
        await TelemetryRepository.create(
            category='page', event_type='page.view', path='/home', user_id=u1.id,
        )
        top = {r['path']: r for r in await TelemetryService().top_paths(staff)}
        assert top['/admin']['views'] == 3
        assert top['/admin']['users'] == 2
        assert top['/home']['views'] == 1
        assert top['/home']['users'] == 1

    async def test_top_paths_excludes_non_page_categories(self, db):
        staff = await _staff()
        await TelemetryRepository.create(
            category='domain', event_type='match.created', path=None, user_id=staff.id,
        )
        assert await TelemetryService().top_paths(staff) == []

    async def test_top_event_types(self, db):
        staff = await _staff()
        await TelemetryRepository.create(category='domain', event_type='match.created', user_id=staff.id)
        await TelemetryRepository.create(category='domain', event_type='match.created', user_id=staff.id)
        await TelemetryRepository.create(category='interaction', event_type='report.viewed', path='audit', user_id=staff.id)
        by_evt = {r['event_type']: r for r in await TelemetryService().top_event_types(staff)}
        assert by_evt['match.created']['count'] == 2
        assert by_evt['match.created']['category'] == 'domain'
        assert by_evt['report.viewed']['count'] == 1

    async def test_top_users_resolves_names_and_sessions(self, db):
        staff = await _staff()
        u1 = await _plain(4001, 'alice')
        await TelemetryRepository.create(category='page', event_type='page.view', path='/x', user_id=u1.id, session_id='s1')
        await TelemetryRepository.create(category='page', event_type='page.view', path='/y', user_id=u1.id, session_id='s1')
        await TelemetryRepository.create(category='page', event_type='page.view', path='/z', user_id=u1.id, session_id='s2')
        rows = await TelemetryService().top_users(staff)
        alice = next(r for r in rows if r['user_id'] == u1.id)
        assert alice['events'] == 3
        assert alice['sessions'] == 2
        assert alice['user'] == 'alice'

    async def test_engagement_summary(self, db):
        staff = await _staff()
        u1 = await _plain(5001, 'a')
        await TelemetryRepository.create(category='page', event_type='page.view', path='/a', user_id=u1.id, session_id='s1')
        await TelemetryRepository.create(category='interaction', event_type='report.viewed', path='audit', user_id=u1.id, session_id='s1')
        await TelemetryRepository.create(category='domain', event_type='match.created', user_id=None)
        summary = await TelemetryService().engagement_summary(staff)
        assert summary['total_events'] == 3
        assert summary['unique_users'] == 1  # the domain row has a null user
        assert summary['unique_sessions'] == 1
        assert summary['page_views'] == 1


# ---------------------------------------------------------------------------
# list / count filters + Staff gating
# ---------------------------------------------------------------------------


class TestListAndCount:
    async def test_filters(self, db):
        staff = await _staff()
        await TelemetryRepository.create(category='page', event_type='page.view', path='/admin', user_id=staff.id)
        await TelemetryRepository.create(category='domain', event_type='match.created', user_id=staff.id)
        svc = TelemetryService()
        assert await svc.count_events(staff) == 2
        assert await svc.count_events(staff, category='page') == 1
        assert await svc.count_events(staff, path_contains='adm') == 1
        rows = await svc.list_events(staff, category='domain')
        assert len(rows) == 1
        assert rows[0].event_type == 'match.created'


class TestStaffGating:
    async def test_reads_require_staff(self, db):
        plain = await _plain()
        svc = TelemetryService()
        with pytest.raises(PermissionError):
            await svc.list_events(plain)
        with pytest.raises(PermissionError):
            await svc.count_events(plain)
        with pytest.raises(PermissionError):
            await svc.engagement_summary(plain)
        with pytest.raises(PermissionError):
            await svc.top_paths(plain)
        with pytest.raises(PermissionError):
            await svc.top_event_types(plain)
        with pytest.raises(PermissionError):
            await svc.top_users(plain)

    async def test_staff_reads_allowed(self, db):
        staff = await _staff()
        assert await TelemetryService().count_events(staff) == 0
