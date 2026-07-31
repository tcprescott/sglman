"""Async-qualifier config substrate — validated JSON blob (PR 9).

Mirrors :mod:`application.services.tournament_config`: worker-/query-facing knobs
(``opens_at``/``closes_at``, ``runs_per_pool``, ``allowed_reattempts``) are typed
columns on :class:`~models.AsyncQualifier`; scoring parameters, the draw-fairness
threshold, and messaging templates live in the schema-validated ``config`` blob.
``extra='forbid'`` keeps it a closed, reviewed vocabulary.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from application.utils.config_validation import validate_config_blob


class AsyncQualifierConfig(BaseModel):
    """Validated shape of ``AsyncQualifier.config`` (every field optional)."""

    model_config = ConfigDict(extra='forbid')

    # Number of fastest approved runs averaged into a permalink's par.
    par_sample_size: Optional[int] = Field(default=None, ge=1)
    # Play-count gap (max−min across a pool's permalinks) at which the draw stops
    # being random and forces the least-played permalink, keeping sampling even.
    draw_imbalance_threshold: Optional[int] = Field(default=None, ge=1)
    # How long a drawn run may stay in progress before the worker forfeits it.
    # A run that is never submitted otherwise holds its permalink assignment and
    # the player's pool slot forever, and — because a claimed finish time is only
    # checked against the wall clock since the draw — an indefinitely-open run
    # also lets any finish time be claimed. Null falls back to
    # ``DEFAULT_RUN_TIME_LIMIT_HOURS``; the ceiling is a week, matching the
    # submitted-time bound.
    run_time_limit_hours: Optional[int] = Field(default=None, ge=1, le=168)
    # How long before that deadline the runner is warned. Null falls back to
    # ``DEFAULT_EXPIRY_WARNING_MINUTES``.
    expiry_warning_minutes: Optional[int] = Field(default=None, ge=1)
    # Safe ``{placeholder}`` templates for DM notifications (never eval).
    messaging_templates: Optional[Dict[str, str]] = None


def validate_async_qualifier_config(
    config: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Validate/normalize an ``AsyncQualifier.config`` blob (None passes through)."""
    return validate_config_blob(config, AsyncQualifierConfig, "qualifier")
