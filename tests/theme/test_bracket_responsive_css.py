"""Regression guards for the bracket stylesheet's responsive + theming contract.

``static/css/brackets.css`` carries invariants the Python tests can't otherwise
reach, and each one here encodes a defect that actually shipped:

* the 2-D bracket and the phone accordion draw the same graph, so showing both
  duplicates every match — the accordion was *revealed* below ``lt.md`` while
  nothing ever hid the 2-D view, because ``.bracket-2d`` had no rule at all;
* ``.bracket-match-flow`` was ``position: static``, leaving the absolutely
  positioned match-number badge without a containing block, so every round's
  badges stacked on one spot instead of sitting on their own cards;
* the ``--bracket-*`` properties sat on ``:root``, where ``var(--q-primary)``
  resolves to Quasar's stock blue — ``ui.colors()`` writes the tenant palette
  onto ``body``, so the winner accent ignored the community's brand.

These assert the shape of the rules, not their exact formatting, so ordinary
edits to the stylesheet don't trip them.
"""

import re
from pathlib import Path

import pytest

CSS_PATH = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'brackets.css'

# Quasar's lt.md breakpoint — the width the two bracket views swap at.
MOBILE_MEDIA = '@media (max-width: 1023px)'


@pytest.fixture(scope='module')
def css() -> str:
    """The stylesheet with /* … */ comments stripped.

    The comments explain the very declarations asserted below (and quote the
    values that must *not* appear), so matching against them would be circular.
    """
    return re.sub(r'/\*.*?\*/', '', CSS_PATH.read_text(), flags=re.DOTALL)


def _block(css: str, opener: str) -> str:
    """The body of the brace-balanced block starting at ``opener``."""
    start = css.index(opener) + len(opener)
    depth, i = 1, start
    while depth:
        if css[i] == '{':
            depth += 1
        elif css[i] == '}':
            depth -= 1
        i += 1
    return css[start:i - 1]


def _display_of(block: str, selector: str) -> str | None:
    """The ``display`` value a rule for exactly ``selector`` sets, if any."""
    for match in re.finditer(
        re.escape(selector) + r'\s*\{([^}]*)\}', block,
    ):
        decl = re.search(r'display:\s*([\w-]+)', match.group(1))
        if decl:
            return decl.group(1)
    return None


def test_desktop_shows_the_2d_bracket_and_hides_the_accordion(css: str) -> None:
    assert _display_of(css, '.bracket-mobile-list') == 'none'
    assert _display_of(css, '.bracket-view-toggle') == 'none'


def test_mobile_swaps_the_two_views(css: str) -> None:
    """Below lt.md the accordion leads and the 2-D bracket is hidden.

    Both halves matter: revealing the accordion without hiding the 2-D bracket
    is what rendered every match twice on a phone.
    """
    mobile = _block(css, MOBILE_MEDIA + ' {')
    assert _display_of(mobile, '.bracket-2d') == 'none'
    assert _display_of(mobile, '.bracket-mobile-list') == 'block'


def test_mobile_toggle_opts_back_into_the_2d_bracket(css: str) -> None:
    """The List/Bracket toggle swaps them, so exactly one is ever visible."""
    mobile = _block(css, MOBILE_MEDIA + ' {')
    assert _display_of(mobile, '.bracket-views.view-bracket .bracket-2d') == 'block'
    assert _display_of(mobile, '.bracket-views.view-bracket .bracket-mobile-list') == 'none'


def test_flow_card_is_a_containing_block_for_its_match_number(css: str) -> None:
    body = _block(css, '.bracket-match.bracket-match-flow {')
    position = re.search(r'position:\s*(\w+)', body)
    assert position is not None, 'the flow card must set an explicit position'
    assert position.group(1) != 'static', (
        'a static flow card gives .bracket-match-num (position: absolute) no '
        'containing block, stacking every round\'s badges on one spot'
    )


def test_bracket_variables_are_declared_where_ui_colors_writes_the_palette(css: str) -> None:
    """The accent must resolve against body's --q-primary, not :root's."""
    assert '--bracket-accent' in _block(css, '\nbody {')
    assert '--bracket-accent' not in css.split('\nbody {')[0], (
        'declaring --bracket-* on :root resolves var(--q-primary) against '
        "Quasar's stock blue instead of the tenant palette on <body>"
    )


def test_standings_rows_share_one_width_so_columns_align(css: str) -> None:
    """Per-row max-content sizing stair-stepped W-L-D/Pts down the table."""
    body = _block(css, '.bracket-strow {')
    assert 'min-width: max-content' not in body
    assert 'min-width: 100%' in body
