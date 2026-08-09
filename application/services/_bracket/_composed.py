"""What every bracket mixin may assume the composed service provides.

Each mixin in this package is code motion out of ``bracket_service.py`` and
reaches ``self.repository`` / ``self.audit_service`` — attributes that
:class:`~application.services.bracket_service.BracketService.__init__` sets, not
the mixin's own. Every module here already says so in its docstring; this states
it in a form the type checker reads, which is the difference between a prose
claim and a checked one.

The annotations are bare, so nothing exists at runtime and the MRO is unchanged:
a class body annotation without a value only populates ``__annotations__``.

Cross-mixin *method* calls (``_require_bracket``, ``resolve_best_of``,
``_propagate_winner``, …) are deliberately not declared here. Those need real
signatures, and a signature copied into a second place is a signature that
drifts; the collaborator attribute below is stable and carries most of the
weight.

``audit_service`` is the other attribute the composer sets, and is **not**
declared yet on purpose. Declaring it type-checks the ``write_and_publish``
calls, and ten of them across this package then fail: the bracket entry points
take ``actor: Optional[User]`` and pass it straight through, while
``write_and_publish`` requires a ``User`` (see the audit-logging convention in
CLAUDE.md — actor is passed explicitly, never guarded). They are safe at runtime
because ``AuthService.ensure(await AuthService.is_staff(actor))`` rejects a
``None`` actor first, but mypy cannot narrow through that call. Fixing it means
narrowing at each entry point and dropping ``Optional`` from the internal
signatures — a change worth making on its own, not as a side effect of this one.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.repositories import BracketRepository


class ComposedBracketService:
    """Base for the bracket mixins: the collaborators the composer owns."""

    if TYPE_CHECKING:
        repository: 'BracketRepository'
