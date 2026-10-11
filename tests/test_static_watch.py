"""The cached Watch page at ``/live``.

What a stranger from a tweet sees: stream links always, player names only where
staff opened today's schedule to non-members (the same switch as the join
door's preview), and nothing that needs a socket or a sign-in.
"""

from datetime import time

import pages.static_brackets as static_brackets
import pages.static_watch as static_watch
from application.services.system_config_service import KEY_JOIN_PREVIEW, SystemConfigService
from application.tenant_context import tenant_scope
from middleware.auth import _matches_protected_route
from middleware.public_cache import _drop_cookie_vary, is_public_cacheable_path
from models import GeneratedSeeds, Match, MatchPlayers, Role, Stage, Tournament, UserRole
from tests.conftest import DEFAULT_TEST_TENANT_ID
from tests.factories import make_user
from theme.watch_view import WatchMatch, WatchStage, WatchView, render_watch_document


async def _staff():
    user = await make_user(discord_id=8001, username='staff-watch')
    await UserRole.create(user=user, role=Role.STAFF, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


async def _match_on(stage: Stage, hour: int, *, seated: bool = False) -> Match:
    from application.utils.timezone import combine_local, now_local, today_local

    tournament = await Tournament.create(name='Cup')
    match = await Match.create(
        tournament=tournament, stage=stage,
        scheduled_at=combine_local(today_local(), time(hour, 0)),
        seated_at=now_local() if seated else None,
        generated_seed=await GeneratedSeeds.create(
            seed_url='https://alttpr.com/h/abcd1234', generator='alttpr',
        ),
    )
    for n in (1, 2):
        player = await make_user(
            discord_id=8100 + match.id * 10 + n, username=f'w{match.id}-{n}',
            display_name=f'Runner {match.id}-{n}',
        )
        await MatchPlayers.create(match=match, user=player)
    return match


class TestBuildWatchView:
    async def test_stream_links_show_but_names_stay_hidden_by_default(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            stage = await Stage.create(
                name='Main Stage', stream_url='https://twitch.tv/main',
                tenant_id=DEFAULT_TEST_TENANT_ID,
            )
            await _match_on(stage, 23, seated=True)
            view = await static_watch.build_watch_view(DEFAULT_TEST_TENANT_ID, '/t/default')

        assert [s.name for s in view.stages] == ['Main Stage']
        assert view.stages[0].stream_url == 'https://twitch.tv/main'
        assert len(view.stages[0].on_now) == 1
        assert view.stages[0].on_now[0].players is None
        body = render_watch_document(view)
        assert 'Runner' not in body
        assert 'https://twitch.tv/main' in body

    async def test_names_follow_the_staff_switch(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            await SystemConfigService.set_raw(KEY_JOIN_PREVIEW, 'true', await _staff())
            stage = await Stage.create(name='Main Stage', tenant_id=DEFAULT_TEST_TENANT_ID)
            await _match_on(stage, 23)
            view = await static_watch.build_watch_view(DEFAULT_TEST_TENANT_ID, '')

        assert view.stages[0].on_now == []
        assert ' vs ' in view.stages[0].up_next[0].players

    async def test_a_stage_with_no_stream_and_nothing_today_is_left_out(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            await Stage.create(name='Spare', tenant_id=DEFAULT_TEST_TENANT_ID)
            view = await static_watch.build_watch_view(DEFAULT_TEST_TENANT_ID, '')
        assert view.stages == []


class TestRender:
    def test_user_text_is_escaped_and_unsafe_links_are_not_drawn(self):
        body = render_watch_document(WatchView(
            community='<b>Com</b>',
            stages=[WatchStage(
                name='<img src=x onerror=alert(1)>',
                stream_url='javascript:alert(1)',
                up_next=[WatchMatch(time='19:00', tournament='T', players='<script>x</script>')],
            )],
        ))
        assert '<img src=x' not in body
        assert '<script>x' not in body
        assert 'javascript:' not in body
        assert '&lt;b&gt;Com&lt;/b&gt;' in body

    def test_links_carry_the_tenant_prefix(self):
        body = render_watch_document(WatchView(
            community='C', tournaments=[(3, 'Cup')], root_path='/t/sgl',
            crew_signup_path='/home/schedule', event_info=True,
        ))
        assert 'href="/t/sgl/live/tournament/3/brackets"' in body
        assert 'href="/t/sgl/home/schedule"' in body
        assert 'href="/t/sgl/event-info"' in body


class TestRoute:
    def test_registered_anonymous_and_cookie_free(self):
        static_watch.create()
        from nicegui import app

        assert '/live' in {getattr(r, 'path', None) for r in app.routes}
        assert not _matches_protected_route('/live')
        assert is_public_cacheable_path('/live')
        assert is_public_cacheable_path('/t/sgl/live')
        assert is_public_cacheable_path('/t/sgl/live/')
        assert not is_public_cacheable_path('/t/sgl/lively')

    def test_match_events_invalidate_it(self):
        from application.events import Event, EventType

        static_brackets._cache.put(21, static_watch._CACHE_KEY, 'cached')
        with tenant_scope(21):
            static_brackets._on_change(Event.create(EventType.MATCH_STARTED, {'match_id': 1}))
        assert static_brackets._cache.get(21, static_watch._CACHE_KEY) is None


def test_vary_cookie_is_dropped_so_a_cdn_can_share_one_entry():
    assert _drop_cookie_vary(b'Accept-Encoding, Cookie, Accept-Encoding') == b'Accept-Encoding'
    assert _drop_cookie_vary(b'Cookie') == b''
