"""Display labels for a bracket's format and state.

One home for chrome three surfaces need identically: the public stage index and
detail (``pages/brackets.py``), the anonymous browse tab
(``pages/home_tabs/brackets.py``), and the admin create dialog's format select
(``pages/admin_tabs/admin_brackets.py``) — which had each grown its own copy.
"""

from models import BracketFormat, BracketState

FORMAT_LABELS: dict[BracketFormat, str] = {
    BracketFormat.SINGLE_ELIM: 'Single elimination',
    BracketFormat.DOUBLE_ELIM: 'Double elimination',
    BracketFormat.SWISS: 'Swiss',
    BracketFormat.ROUND_ROBIN: 'Round robin',
}

# Keyed by the enum's *value* for ``ui.select``, whose options map raw values.
FORMAT_OPTIONS: dict[str, str] = {
    fmt.value: label for fmt, label in FORMAT_LABELS.items()
}

STATE_COLORS: dict[BracketState, str] = {
    BracketState.DRAFT: 'grey',
    BracketState.ACTIVE: 'positive',
    BracketState.COMPLETE: 'primary',
}


def format_label(fmt: BracketFormat) -> str:
    return FORMAT_LABELS.get(fmt, getattr(fmt, 'value', str(fmt)))


def state_color(state: BracketState) -> str:
    return STATE_COLORS.get(state, 'grey')
