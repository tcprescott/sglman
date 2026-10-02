"""Source-shape guards for player-journey fixes the SQLite suite cannot drive.

Each was a live bug found by driving the app (docs/reviews/player-journey-ux.md)
in code that only runs inside a NiceGUI client, so the assertion is on the shape
of the call rather than its behaviour.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO / rel).read_text()


class TestTriforceButton:
    def test_the_card_hands_the_client_to_the_dialog(self):
        # A background task has an empty slot stack: ui.dialog() raised and the
        # button did nothing. check_slot_context cannot see this one because the
        # coroutine is imported, not defined beside its call site.
        source = _read('pages/home_tabs/tournaments.py')
        assert 'open_triforce_dialog(tourney, user, context.client)' in source

    def test_the_dialog_reenters_the_client(self):
        source = _read('pages/home_tabs/triforce_texts.py')
        opener = source[source.index('async def open_triforce_dialog'):]
        opener = opener[:opener.index('\nasync def ', 1)]
        assert 'with client:' in opener


class TestBookingCopy:
    """A player's booking is final; nothing asks the opponent to confirm it."""

    def test_no_surface_promises_a_confirm_step(self):
        for rel in ('pages/home_tabs/player.py',
                    'theme/dialog/bracket_schedule_dialog.py',
                    'theme/dialog/challonge_schedule_dialog.py'):
            source = _read(rel)
            assert 'your opponent confirms' not in source, rel
            assert 'asked to confirm' not in source, rel
            assert 'ask staff to move it' in source, rel

    def test_the_board_refreshes_before_the_section_holding_the_dialog(self):
        # Rebuilding the section deletes the dialog the callback runs from, and
        # the board refresh after it found no tenant ("No tenant in context").
        source = _read('pages/home_tabs/player.py')
        for section in ('challonge_section', 'bracket_section'):
            after = source[source.index(f'{section}.refresh()') - 120:source.index(f'{section}.refresh()')]
            assert 'await table_view.refresh()' in after, section


class TestBookingDialog:
    def test_on_submit_runs_in_the_opening_client_and_tenant(self):
        source = _read('theme/dialog/bracket_schedule_dialog.py')
        assert 'self._client = context.client' in source
        assert 'self.tenant_id = get_current_tenant_id()' in source
        assert 'with self._client, self._scope():' in source

    def test_a_lost_race_closes_and_refreshes(self):
        source = _read('theme/dialog/bracket_schedule_dialog.py')
        branch = source[source.index('except AlreadyBookedError'):]
        branch = branch[:branch.index('except PermissionError')]
        assert 'dialog.close()' in branch
        assert 'return' not in branch  # falls through to _after_submit

    def test_no_dialog_defaults_to_now(self):
        for rel in ('theme/dialog/bracket_schedule_dialog.py',
                    'theme/dialog/challonge_schedule_dialog.py'):
            source = _read(rel)
            assert 'next_whole_hour_local()' in source, rel
            assert 'now_local()' not in source, rel
