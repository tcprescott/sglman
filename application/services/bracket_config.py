"""Bracket config substrate — the schema-validated shape of ``Bracket.config``.

Native brackets keep their per-stage knobs — grand-final reset toggle, Swiss
round count, group count, the scoring points a round robin / Swiss standings pass
consumes, and the tiebreaker order — as a closed, ``extra='forbid'`` JSON blob so
a typo or a stale client field surfaces as a user-facing ``ValueError`` instead
of silently landing dead data. This module owns that schema; the service layer
calls :func:`validate_bracket_config` before persisting the blob.

Advancement config (how a later stage draws from a prior stage's final ranks) is
added by a later unit — this schema deliberately leaves room for it rather than
implementing it now.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from application.utils.config_validation import validate_config_blob


class AdvancementConfig(BaseModel):
    """How a stage draws its field from the prior stage's ``final_rank``.

    Only meaningful on a stage with ``stage_order > 0``; the service reads it
    when staff trigger :meth:`BracketService.advance_stage`. ``count`` entrants
    advance — ``count`` per source ``group_number`` when ``per_group``, else the
    ``count`` best overall. ``seeding`` chooses how the advancers seed into this
    stage: ``'snake'`` (default) spreads group winners and keeps two entrants
    from the same source group apart in the opening playoff round; ``'preserve'``
    seeds strictly in advancement (rank) order.
    """

    model_config = ConfigDict(extra='forbid')

    count: int
    per_group: bool = False
    seeding: str = 'snake'

    @field_validator('count')
    @classmethod
    def _count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("advancement count must be at least 1")
        return v

    @field_validator('seeding')
    @classmethod
    def _seeding_known(cls, v: str) -> str:
        if v not in ('snake', 'preserve'):
            raise ValueError("advancement seeding must be 'snake' or 'preserve'")
        return v


class BracketConfig(BaseModel):
    """Validated shape of ``Bracket.config``.

    ``extra='forbid'`` is load-bearing: it is what turns an unknown key into a
    validation error, keeping the config a closed, reviewed vocabulary rather
    than a free-form bag. Every field is optional so a stage opts into only the
    behavior it uses.
    """

    model_config = ConfigDict(extra='forbid')

    # Double elimination: persist and activate the grand-final reset match only
    # when the losers-bracket entrant wins the first grand final.
    grand_final_reset: bool = True
    # Swiss: number of rounds to run (None = derived by a later unit).
    swiss_rounds: Optional[int] = None
    # Round robin: how many balanced groups to split the field into.
    group_count: Optional[int] = None
    # Scoring parameters a round-robin / Swiss standings pass consumes.
    win_points: float = 1.0
    draw_points: float = 0.5
    loss_points: float = 0.0
    bye_points: float = 1.0
    # Ordered tiebreaker keys the standings pass applies.
    tiebreakers: Optional[List[str]] = None
    # Opponents'-match-win floor for OMW% tiebreakers (standard 1/3).
    omw_floor: float = 1 / 3
    # Multi-stage chaining: how a non-first stage draws its field from the prior
    # stage's final ranks (None on a single-stage or first stage).
    advancement: Optional[AdvancementConfig] = None


def validate_bracket_config(
    config: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Validate and normalize a ``Bracket.config`` blob.

    Returns ``None`` unchanged (config is optional). Otherwise validates the dict
    against :class:`BracketConfig` and returns the normalized dict with unset
    keys dropped. Raises :class:`ValueError` on any unknown key or bad value, so
    the service layer can surface it the same as every other user error.
    """
    return validate_config_blob(config, BracketConfig, "bracket")
