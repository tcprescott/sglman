"""The room seeds route: reachable without a login, useless without a token.

The page is anonymous by design — a shared machine in a public room has nobody
signed in on it — so ``AuthMiddleware`` must not bounce it to ``/login``. What
stands in for the session is the token in the path, and everything a bad token
can be (unknown, revoked, wrong community, malformed) has to look identical
from outside.
"""

from middleware.auth import _matches_protected_route, _tracked_params


class TestRouteRegistration:
    def test_the_seeds_route_is_not_login_gated(self):
        import pages.room_seeds as room_seeds

        room_seeds.create()

        assert not _matches_protected_route('/room/wizzrobe_room_abc/seeds')

    def test_the_page_resolves_the_token_before_it_renders_anything(self):
        """Pins the ordering: no board is built for a token that opens nothing."""
        from pathlib import Path

        source = Path('pages/room_seeds.py').read_text()
        assert source.index('RoomTokenService().resolve') < source.index('MatchTableView(')


class TestTelemetryRedaction:
    """A page-view row must never become a key ring."""

    def test_a_token_path_param_is_redacted(self):
        assert _tracked_params({'token': 'wizzrobe_room_supersecret'}) == {
            'token': '[redacted]',
        }

    def test_ordinary_params_are_still_recorded(self):
        assert _tracked_params({'tournament_id': 7, 'section': 'schedule'}) == {
            'tournament_id': '7', 'section': 'schedule',
        }

    def test_long_values_stay_bounded_and_nones_are_dropped(self):
        params = _tracked_params({'q': 'x' * 500, 'missing': None})
        assert len(params['q']) == 120
        assert 'missing' not in params
