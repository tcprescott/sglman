"""The offline banner's copy, its body-class hook, and its four event bindings.

No unit test can prove what a browser does with a dead socket — that is a
re-measurement pass. What *can* be locked here is the contract the rest of the
offline story hangs off: the exact copy an operator reads, the single body class
the CSS and the click guard both key on, and the fact that all four detection
signals are wired. Losing any one of the four silently halves the detection: the
window events miss "server unreachable, link up", and the socket events miss the
first seconds of a dead link.
"""

from theme.connection import (
    BLOCKED_ACTION_TEXT,
    OFFLINE_BANNER_TEXT,
    OFFLINE_BODY_CLASS,
    ONLINE_BANNER_TEXT,
    REQUIRES_SOCKET_CLASS,
    connection_watch_script,
)


class TestCopy:
    def test_offline_text_says_what_it_means_for_the_operator(self):
        assert OFFLINE_BANNER_TEXT == "No connection — actions won't be saved. Reconnecting…"

    def test_recovery_text_is_the_one_word_that_matters(self):
        assert ONLINE_BANNER_TEXT == 'Back online.'

    def test_blocked_action_text_says_it_was_not_sent(self):
        assert BLOCKED_ACTION_TEXT == 'No connection — not sent. Try again when the banner clears.'

    def test_no_copy_mentions_the_socket(self):
        for text in (OFFLINE_BANNER_TEXT, ONLINE_BANNER_TEXT, BLOCKED_ACTION_TEXT):
            assert 'socket' not in text.lower()

    def test_every_string_reaches_the_script(self):
        script = connection_watch_script()
        for text in (OFFLINE_BANNER_TEXT, ONLINE_BANNER_TEXT, BLOCKED_ACTION_TEXT):
            # json.dumps escapes the non-ASCII copy, so compare on the escaped form.
            import json
            assert json.dumps(text) in script


class TestDetection:
    def test_listens_to_both_window_events(self):
        script = connection_watch_script()
        assert "window.addEventListener('offline'" in script
        assert "window.addEventListener('online'" in script

    def test_listens_to_both_socket_events(self):
        script = connection_watch_script()
        assert "window.socket.on('disconnect'" in script
        assert "window.socket.on('connect'" in script

    def test_tolerates_a_socket_that_does_not_exist_yet(self):
        # window.socket is assigned in nicegui.js's mounted(), which can run
        # after this snippet is parsed.
        script = connection_watch_script()
        assert 'if (window.socket && window.socket.on)' in script
        assert 'setTimeout(bindSocket' in script

    def test_installs_only_once_per_document(self):
        script = connection_watch_script()
        assert 'window.__wizConnectionWatch' in script


class TestHooks:
    def test_toggles_the_single_body_class(self):
        script = connection_watch_script()
        assert f'"{OFFLINE_BODY_CLASS}"' in script
        assert 'document.body.classList.add(OFFLINE_CLASS)' in script
        assert 'document.body.classList.remove(OFFLINE_CLASS)' in script

    def test_refuses_marked_controls_in_the_capture_phase(self):
        script = connection_watch_script()
        assert f'"{REQUIRES_SOCKET_CLASS}"' in script
        assert 'e.stopImmediatePropagation()' in script
        # The listener must be registered with capture=true, i.e. before Vue's.
        assert '}, true);' in script

    def test_explains_the_refusal_without_the_socket(self):
        # ui.notify would travel over the very socket that is down.
        script = connection_watch_script()
        assert 'Quasar.Notify.create' in script

    def test_leaves_the_framework_popup_alone(self):
        script = connection_watch_script()
        assert 'popup' not in script
