"""What the MCP consent card tells a person before they approve.

Client registration is open by design (RFC 7591 is what lets a client configure
itself from a URL), so ``client_name`` is a string the requester picked and
proves nothing — anyone can register a client called "Claude". The redirect URI
is the part that cannot be faked, because it is where the authorization code
actually goes. Showing it is the whole defence against a consent screen that
reads as trustworthy while handing a stranger a working token.
"""

from pages.mcp_consent import _redirect_target


class TestRedirectTarget:
    def test_https_uri_shows_host(self):
        assert _redirect_target('https://claude.ai/api/mcp/auth_callback') == 'claude.ai'

    def test_port_is_kept(self):
        """A loopback client is identified by its port, so it has to survive."""
        assert _redirect_target('http://localhost:9999/callback') == 'localhost:9999'

    def test_query_string_is_dropped(self):
        assert _redirect_target('https://evil.test/cb?next=claude.ai') == 'evil.test'

    def test_lookalike_host_is_shown_verbatim(self):
        """The case the card exists for: the name says Claude, the address doesn't."""
        assert _redirect_target('https://claude.ai.evil.test/cb') == 'claude.ai.evil.test'

    def test_custom_scheme_falls_back_to_the_whole_uri(self):
        """A native client has no netloc; showing nothing would be worse than noise."""
        assert _redirect_target('cursor://anysphere.cursor-mcp/oauth') == (
            'cursor://anysphere.cursor-mcp/oauth'
        )

    def test_missing_uri_still_reads_as_a_sentence(self):
        assert _redirect_target('') == 'an unknown address'
