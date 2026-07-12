"""Pure tenant-URL path helpers (``application/utils/tenant_urls.py``).

These guard the path-mode return-target logic: a shared-cookie login must land
back inside the *originating* tenant, never a different community whose stale
referrer is still in the session.
"""

from application.utils.tenant_urls import sanitize_return_path, tenant_home


class TestTenantHome:
    def test_path_mode(self):
        assert tenant_home('/t/sgl') == '/t/sgl/'

    def test_bare_platform_host(self):
        assert tenant_home('') == '/'


class TestSanitizeReturnPath:
    def test_honors_referrer_within_same_tenant(self):
        assert sanitize_return_path('/t/sgl', '/t/sgl/admin') == '/t/sgl/admin'

    def test_honors_referrer_with_query_within_tenant(self):
        assert sanitize_return_path('/t/sgl', '/t/sgl/admin?tab=Challonge') == '/t/sgl/admin?tab=Challonge'

    def test_rejects_referrer_from_other_tenant(self):
        # Stale referrer for a *different* community -> fall back to this home.
        assert sanitize_return_path('/t/sgl', '/t/other/admin') == '/t/sgl/'

    def test_rejects_referrer_that_is_a_prefix_lookalike(self):
        # '/t/sglother' must not be treated as belonging to '/t/sgl'.
        assert sanitize_return_path('/t/sgl', '/t/sglother/admin') == '/t/sgl/'

    def test_rejects_auth_route_referrer(self):
        assert sanitize_return_path('/t/sgl', '/t/sgl/login') == '/t/sgl/'
        assert sanitize_return_path('/t/sgl', '/t/sgl/oauth/callback') == '/t/sgl/'

    def test_none_referrer_falls_back_to_home(self):
        assert sanitize_return_path('/t/sgl', None) == '/t/sgl/'

    def test_empty_referrer_falls_back_to_home(self):
        assert sanitize_return_path('/t/sgl', '') == '/t/sgl/'

    def test_non_string_referrer_falls_back_to_home(self):
        assert sanitize_return_path('/t/sgl', 12345) == '/t/sgl/'

    def test_bare_host_honors_tenant_qualified_referrer(self):
        # On the bare platform host (root_path='') a tenant-qualified referrer is
        # still a valid onward target (this is how the OAuth callback recovers).
        assert sanitize_return_path('', '/t/sgl/admin') == '/t/sgl/admin'

    def test_bare_host_rejects_auth_route(self):
        assert sanitize_return_path('', '/login') == '/'

    def test_tenant_root_exact_match_is_accepted(self):
        assert sanitize_return_path('/t/sgl', '/t/sgl') == '/t/sgl'
