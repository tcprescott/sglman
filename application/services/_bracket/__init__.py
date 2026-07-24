"""Internal per-concern mixins composed into :class:`BracketService`.

Pure code motion out of ``bracket_service.py`` (which stayed over the repo's
800-line soft limit). Each mixin owns one lifecycle concern; they are combined
by ``BracketService`` and share ``self.repository`` / ``self.audit_service`` and
sibling methods through that single composed class.
"""

from application.services._bracket.advancement import AdvancementMixin
from application.services._bracket.completion import CompletionMixin
from application.services._bracket.generation import GenerationMixin
from application.services._bracket.multistage import MultiStageMixin
from application.services._bracket.scheduling import SchedulingMixin

__all__ = [
    "AdvancementMixin",
    "CompletionMixin",
    "GenerationMixin",
    "MultiStageMixin",
    "SchedulingMixin",
]
