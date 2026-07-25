"""The bracket surface is readable without a login.

Two halves: the route registry that decides whether ``AuthMiddleware`` bounces
an anonymous visitor to ``/login``, and the pure grouping behind the home
Brackets tab that makes those routes reachable without knowing a URL.
"""

from middleware.auth import (
    _matches_protected_route,
    protected_page,
    protected_routes,
    public_page,
)
from pages.home_tabs.brackets import group_by_tournament


class _FakeTournament:
    def __init__(self, name: str):
        self.name = name


class _FakeBracket:
    def __init__(self, bracket_id: int, tournament_id: int, tournament_name: str):
        self.id = bracket_id
        self.tournament_id = tournament_id
        self.tournament = _FakeTournament(tournament_name)


class TestRouteRegistration:
    def test_public_page_is_not_login_gated(self):
        @public_page('/test-public-route')
        async def _page():
            pass

        assert '/test-public-route' not in protected_routes
        assert not _matches_protected_route('/test-public-route')

    def test_protected_page_is_login_gated(self):
        @protected_page('/test-protected-route')
        async def _page():
            pass

        assert '/test-protected-route' in protected_routes
        assert _matches_protected_route('/test-protected-route')

    def test_bracket_routes_are_reachable_anonymously(self):
        """The whole point: neither bracket route redirects to /login."""
        import pages.brackets as bracket_pages

        bracket_pages.create()

        assert not _matches_protected_route('/brackets/7')
        assert not _matches_protected_route('/tournament/3/brackets')


class TestGroupByTournament:
    def test_groups_stages_under_their_tournament(self):
        rows = [
            _FakeBracket(1, 10, 'Spring Cup'),
            _FakeBracket(2, 10, 'Spring Cup'),
            _FakeBracket(3, 20, 'Winter Cup'),
        ]
        grouped = group_by_tournament(rows)
        assert [(tid, name) for tid, name, _ in grouped] == [
            (10, 'Spring Cup'), (20, 'Winter Cup'),
        ]
        assert [[b.id for b in stages] for _, _, stages in grouped] == [[1, 2], [3]]

    def test_preserves_query_order(self):
        """The repository orders active-first, then name — grouping keeps it."""
        rows = [_FakeBracket(1, 20, 'Winter Cup'), _FakeBracket(2, 10, 'Spring Cup')]
        assert [tid for tid, _, _ in group_by_tournament(rows)] == [20, 10]

    def test_empty(self):
        assert group_by_tournament([]) == []
