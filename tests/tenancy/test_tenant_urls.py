"""Pure tenant-URL path helpers (``application/utils/tenant_urls.py``).

These guard the path-mode return-target logic: a shared-cookie login must land
back inside the *originating* tenant, never a different community whose stale
referrer is still in the session.
"""

from application.utils.tenant_urls import sanitize_return_path, strip_root_path, tenant_home


class TestTenantHome:
    def test_path_mode(self):
        assert tenant_home('/t/sgl') == '/t/sgl/'

    def test_bare_platform_host(self):
        assert tenant_home('') == '/'


class TestStripRootPath:
    """The client-side navigate contract.

    ``nicegui.js`` prepends the client's ``options.prefix`` to every absolute
    path handed to ``ui.navigate.to``::

        open: (msg) => { const url = msg.path.startsWith("/") ? options.prefix + msg.path : msg.path; ... }

    That is the framework's behaviour, not a bug to route around: most of this
    codebase relies on it (see the comments in ``theme/dialog/qr_label_dialog.py``
    and ``theme/tables/match_slots.py``). The fix for a doubled prefix is to hand
    it a **tenant-local** path — never to re-add the prefix here. If a future
    reader "fixes" this helper by prepending ``root_path``, these tests fail.
    """

    def test_strips_the_prefix_in_path_mode(self):
        assert strip_root_path('/t/sgl', '/t/sgl/equipment/3') == '/equipment/3'

    def test_never_returns_a_path_that_still_carries_the_prefix(self):
        for path in ('/t/sgl', '/t/sgl/', '/t/sgl/equipment/3'):
            assert not strip_root_path('/t/sgl', path).startswith('/t/sgl')

    def test_tenant_root_becomes_the_local_root(self):
        assert strip_root_path('/t/sgl', '/t/sgl') == '/'
        assert strip_root_path('/t/sgl', '/t/sgl/') == '/'

    def test_keeps_the_query_string(self):
        assert strip_root_path('/t/sgl', '/t/sgl/admin?tab=equipment') == '/admin?tab=equipment'

    def test_host_mode_passes_through_untouched(self):
        # On a custom domain root_path is '' and options.prefix is empty too.
        assert strip_root_path('', '/equipment/3') == '/equipment/3'

    def test_a_path_outside_the_prefix_is_left_alone(self):
        assert strip_root_path('/t/sgl', '/t/other/equipment/3') == '/t/other/equipment/3'

    def test_a_prefix_lookalike_is_not_stripped(self):
        assert strip_root_path('/t/sgl', '/t/sglother/admin') == '/t/sglother/admin'

    def test_degenerate_inputs_fall_back_to_the_local_root(self):
        assert strip_root_path('/t/sgl', '') == '/'
        assert strip_root_path('/t/sgl', None) == '/'
        assert strip_root_path('/t/sgl', 12345) == '/'

    def test_a_missing_root_path_is_tolerated(self):
        assert strip_root_path(None, '/equipment/3') == '/equipment/3'


class TestSanitizeReturnPath:
    def test_honors_referrer_within_same_tenant(self):
        assert sanitize_return_path('/t/sgl', '/t/sgl/admin') == '/t/sgl/admin'

    def test_honors_referrer_with_query_within_tenant(self):
        assert sanitize_return_path('/t/sgl', '/t/sgl/admin/reports?report=capacity') == '/t/sgl/admin/reports?report=capacity'

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
