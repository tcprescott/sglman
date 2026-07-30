"""What the admin's confirm-a-result dialog actually says.

Confirming is the step that settles a match and advances the bracket, and it is
worked as a queue — so the dialog has to carry the decision (who won) and, for a
flagged result, the proctor's reason. It used to say only "Confirm the recorded
result for match #3?" followed by both player names, which is the same sentence
for a clean result and a disputed one.

``confirm_result_message`` is pure so it can be checked without a NiceGUI client;
the players it reads are plain attribute holders, matching the prefetched
``players__user`` shape.
"""

from types import SimpleNamespace

from theme.tables.match_lifecycle import confirm_result_message


def player(name: str, *, rank=None):
    return SimpleNamespace(finish_rank=rank, user=SimpleNamespace(preferred_name=name))


def match(*players, needs_review=False, review_note=None, match_id=7):
    return SimpleNamespace(
        id=match_id, players=list(players),
        needs_review=needs_review, review_note=review_note,
    )


class TestWinner:
    def test_names_the_winner_in_the_question(self):
        body = confirm_result_message(match(player('Alice', rank=1), player('Bob')))
        assert body.startswith('Record Alice as the winner of match #7?')

    def test_states_who_beat_whom(self):
        body = confirm_result_message(match(player('Alice', rank=1), player('Bob')))
        assert 'Alice beat Bob.' in body

    def test_winner_order_does_not_matter(self):
        body = confirm_result_message(match(player('Bob'), player('Alice', rank=1)))
        assert body.startswith('Record Alice as the winner of match #7?')
        assert 'Alice beat Bob.' in body

    def test_lists_the_field_when_there_is_more_than_one_loser(self):
        """"X beat Y" would name one of three opponents arbitrarily."""
        body = confirm_result_message(match(
            player('Alice', rank=1), player('Bob'), player('Carol'),
        ))
        assert 'beat' not in body
        assert 'Against: Bob, Carol.' in body

    def test_says_so_when_nothing_is_recorded(self):
        """The service refuses this; the dialog should not imply otherwise."""
        body = confirm_result_message(match(player('Alice'), player('Bob')))
        assert 'No winner is recorded for match #7.' in body
        assert 'Record one before confirming.' in body


class TestDisputeFlag:
    def test_an_unflagged_result_says_nothing_about_review(self):
        body = confirm_result_message(match(player('Alice', rank=1), player('Bob')))
        assert 'review' not in body.lower()

    def test_repeats_the_proctors_note(self):
        body = confirm_result_message(match(
            player('Alice', rank=1), player('Bob'),
            needs_review=True, review_note='Both hit credits within a second.',
        ))
        assert 'Flagged for review by the proctor: Both hit credits within a second.' in body

    def test_says_the_flag_is_bare_when_there_is_no_note(self):
        body = confirm_result_message(match(
            player('Alice', rank=1), player('Bob'), needs_review=True,
        ))
        assert 'with no note' in body

    def test_warns_that_confirming_clears_the_flag(self):
        body = confirm_result_message(match(
            player('Alice', rank=1), player('Bob'), needs_review=True, review_note='n',
        ))
        assert 'Confirming clears the flag.' in body


def test_paragraphs_are_blank_line_separated():
    """``ConfirmationDialog`` renders the body with ``white-space: pre-line``."""
    body = confirm_result_message(match(
        player('Alice', rank=1), player('Bob'), needs_review=True, review_note='n',
    ))
    assert '\n\n' in body
