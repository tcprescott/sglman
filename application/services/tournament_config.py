"""Tournament config substrate - Business Logic Layer.

The hybrid-config decision (docs/online-tournaments) keeps worker-queried knobs
as typed columns on :class:`~models.Tournament` and stores the rest — messaging
templates, scoring parameters, and strategy choices — as a schema-validated JSON
blob in ``Tournament.config``. This module owns that schema.

``validate_tournament_config`` is the single entry point the service layer calls
before persisting the blob. It rejects unknown keys (``extra='forbid'``) so a
typo or a stale client field surfaces as a user-facing ``ValueError`` instead of
silently landing dead data. Feature PRs extend :class:`TournamentConfig` with the
concrete keys their strategies read; PR 0 ships the substrate with only the
cross-cutting messaging-templates facet.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from application.utils.config_validation import validate_config_blob


class TournamentConfig(BaseModel):
    """Validated shape of ``Tournament.config``.

    ``extra='forbid'`` is load-bearing: it is what turns an unknown key into a
    validation error, keeping the config a closed, reviewed vocabulary rather
    than a free-form bag. Every field is optional so an online tournament opts
    into only the behavior it uses.
    """

    model_config = ConfigDict(extra='forbid')

    # Safe templated text for notifications/messages, keyed by template name.
    # Substitution is ``str.format``-style ``{placeholder}`` only — never ``eval``
    # (see the config/code-boundary design constraint). Values are plain strings.
    messaging_templates: Optional[Dict[str, str]] = None


def validate_tournament_config(
    config: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Validate and normalize a ``Tournament.config`` blob.

    Returns ``None`` unchanged (config is optional). Otherwise validates the dict
    against :class:`TournamentConfig` and returns the normalized dict with unset
    keys dropped. Raises :class:`ValueError` on any unknown key or bad value, so
    the service layer can surface it the same as every other user error.
    """
    return validate_config_blob(config, TournamentConfig, "tournament")
