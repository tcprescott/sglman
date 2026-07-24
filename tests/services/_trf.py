"""TRF(x) serialization helpers for Swiss cross-validation (NOT a test module).

Serializes a small deterministic Swiss tournament state to the FIDE TRF(x) text
format that ``bbpPairings --dutch`` consumes, and parses that engine's pairing
output back into ``ref`` tuples. Leading underscore keeps pytest from collecting
it.

Column layout (1-based, mirrors the bbpPairings ``test/tests/*.input`` examples):

* ``001`` at cols 1-3 (player data record marker)
* pairing number, right-justified, cols 5-8
* name, left-justified, cols 15-47
* rating, right-justified, cols 49-52
* points (one decimal, e.g. ``2.0``), right-justified, cols 81-84
* rank (BSN), right-justified, cols 86-89
* then one 10-column block per played round starting at col 91::

      " {opp:>4} {color} {result}"   e.g. "    4 w 1 "

  where ``opp`` is the opponent pairing number (``0000`` for a bye), ``color`` is
  ``w``/``b``/``-`` and ``result`` is ``1``/``0``/``=``/``U`` (win/loss/draw/
  pairing-allocated bye).

A ``012`` header line names the tournament; a trailing ``XXR n`` line declares
the total number of rounds, so the engine pairs round ``rounds_played + 1``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class TrfPlayer:
    """One player's TRF row: pairing number, points, and per-round history.

    ``history`` is one ``(opponent_number, color, result)`` per played round in
    order; ``opponent_number`` is ``0`` for a bye. ``color`` is ``'w'``/``'b'``/
    ``'-'`` and ``result`` is ``'1'``/``'0'``/``'='``/``'U'``.
    """

    number: int
    points: float
    history: List[Tuple[int, str, str]] = field(default_factory=list)
    rating: int = 2000


def _place(buf: List[str], start_col: int, text: str) -> None:
    """Write ``text`` into ``buf`` at 1-based ``start_col``, growing as needed."""
    end = start_col - 1 + len(text)
    if end > len(buf):
        buf.extend(' ' * (end - len(buf)))
    for i, ch in enumerate(text):
        buf[start_col - 1 + i] = ch


def _player_line(p: TrfPlayer) -> str:
    buf: List[str] = list(' ' * 90)
    _place(buf, 1, '001')
    _place(buf, 5, f'{p.number:>4}')
    _place(buf, 15, f'Player{p.number:04d}')
    _place(buf, 49, f'{p.rating:>4}')
    _place(buf, 81, f'{p.points:>4.1f}')
    _place(buf, 86, f'{p.number:>4}')
    line = ''.join(buf)
    blocks = []
    for opp, color, result in p.history:
        opp_txt = '0000' if opp == 0 else f'{opp:>4}'
        blocks.append(f' {opp_txt} {color} {result} ')
    return (line + ''.join(blocks)).rstrip()


def to_trf(
    players: List[TrfPlayer], rounds_played: int, total_rounds: int
) -> str:
    """Serialize a Swiss state to TRF(x) text for ``bbpPairings --dutch``.

    ``rounds_played`` is informational (each player's ``history`` already carries
    exactly that many rounds); ``total_rounds`` becomes the ``XXR`` line so the
    engine pairs the next unplayed round.
    """
    lines = ['012 Wizzrobe Swiss Crossvalidation']
    for p in sorted(players, key=lambda x: x.number):
        lines.append(_player_line(p))
    lines.append(f'XXR {total_rounds}')
    return '\n'.join(lines) + '\n'


def parse_bbp_pairings(
    output_text: str, number_to_ref: Optional[Dict[int, int]] = None
) -> List[Tuple[int, Optional[int]]]:
    """Parse ``bbpPairings -p`` output into ``(ref1, ref2 | None)`` pairings.

    The output's first line is the pairing count; each subsequent line is
    ``white black`` (pairing numbers, ``0`` = bye/unpaired). ``number_to_ref``
    maps pairing numbers back to caller refs (identity when omitted); a ``0``
    opponent becomes ``None``.
    """

    def ref(n: int) -> int:
        return number_to_ref[n] if number_to_ref is not None else n

    lines = [ln for ln in output_text.splitlines() if ln.strip()]
    if not lines:
        return []
    pairings: List[Tuple[int, Optional[int]]] = []
    for ln in lines[1:]:
        parts = ln.split()
        white, black = int(parts[0]), int(parts[1])
        pairings.append((ref(white), None if black == 0 else ref(black)))
    return pairings
