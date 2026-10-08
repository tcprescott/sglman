"""The "Copy Matcherino login" bookmarklet is a self-contained javascript: URL."""

from urllib.parse import unquote

from theme.matcherino_login_card import bookmarklet_href


def test_the_bookmarklet_is_one_encoded_javascript_url():
    href = bookmarklet_href()
    assert href.startswith('javascript:')
    assert not any(c in href for c in ' "<>\n')


def test_the_bookmarklet_only_reads_the_credentials_cookie_on_matcherino():
    script = unquote(bookmarklet_href()[len('javascript:'):])
    assert "startsWith('credentials=')" in script
    assert 'matcherino\\.com$' in script
    assert 'fetch(' not in script and 'XMLHttpRequest' not in script and 'window.open' not in script
