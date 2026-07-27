"""
Randomizer Credential Service - Business Logic Layer

A community's own credentials for the key-gated randomizer APIs, replacing the
former process-wide ``OOTR_API_KEY`` / ``SMMAP_SPOILER_TOKEN`` / ``DK64R_API_KEY``
environment variables. Each tenant supplies the key it was issued, so one
community's quota, spoiler access, and usage terms never ride on another's.

Which credentials exist is declared in :mod:`application.randomizer_credentials`;
this service is the only writer and the only reader of the stored value.

**The secret never leaves this module except at roll time.** ``list_status``
returns configured-or-not, never the value; the audit entries name the credential
and nothing else; :meth:`resolve` is the single unmasked read and is called only
by ``SeedGenerationService`` while rolling. Mutations are gated by
:meth:`AuthService.can_manage_presets` — the same gate as the presets these
credentials serve.
"""

from typing import Any, Dict, List, Optional, Set

from application.randomizer_credentials import all_specs, credentials_for, spec_for
from application.repositories import RandomizerCredentialRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import User


class RandomizerCredentialService:
    """Per-tenant randomizer credentials: status, CRUD, and roll-time resolution."""

    def __init__(self) -> None:
        self.repository = RandomizerCredentialRepository()
        self.audit_service = AuditService()

    async def list_status(self, actor: Optional[User]) -> List[Dict[str, Any]]:
        """One row per declared credential — configured or not, never the value.

        Driven by the registry rather than the stored rows so an unconfigured
        credential still renders with its label and help text.
        """
        await AuthService.ensure_can_manage_presets(actor)
        stored = {(c.randomizer, c.key): c for c in await self.repository.list_all()}
        return [
            {
                'randomizer': spec.randomizer,
                'key': spec.key,
                'label': spec.label,
                'help_text': spec.help_text,
                'configured': (spec.randomizer, spec.key) in stored,
                'updated_at': row.updated_at if (row := stored.get((spec.randomizer, spec.key))) else None,
            }
            for spec in all_specs()
        ]

    async def set_credential(
        self, actor: Optional[User], randomizer: str, key: str, value: str
    ) -> None:
        await AuthService.ensure_can_manage_presets(actor)
        spec = spec_for(randomizer, key)
        value = (value or '').strip()
        if not value:
            raise ValueError(f'A value is required for the {spec.label}')
        replaced = await self.repository.get_by_natural_key(randomizer, key) is not None
        await self.repository.upsert(randomizer, key, value)
        await self.audit_service.write_log(
            actor, AuditActions.RANDOMIZER_CREDENTIAL_SET,
            # Names the credential, never the value or any part of it.
            {'randomizer': randomizer, 'key': key, 'replaced': replaced},
        )

    async def clear_credential(self, actor: Optional[User], randomizer: str, key: str) -> None:
        """Remove a stored credential. Idempotent — clearing an unset one is a no-op."""
        await AuthService.ensure_can_manage_presets(actor)
        spec_for(randomizer, key)
        if not await self.repository.delete_by_natural_key(randomizer, key):
            return
        await self.audit_service.write_log(
            actor, AuditActions.RANDOMIZER_CREDENTIAL_CLEARED,
            {'randomizer': randomizer, 'key': key},
        )

    async def configured_randomizers(self) -> Set[str]:
        """Randomizers whose *every* declared credential this tenant has supplied.

        Feeds ``SeedGenerationService.available_randomizers``; one query.
        """
        pairs = await self.repository.configured_pairs()
        return {
            randomizer
            for randomizer in {r for r, _ in pairs}
            if all((randomizer, spec.key) in pairs for spec in credentials_for(randomizer))
        }

    async def resolve(self, randomizer: str, key: str) -> Optional[str]:
        """The stored secret, unmasked.

        The one path that returns a credential value, and deliberately ungated:
        its only caller is ``SeedGenerationService`` mid-roll, whose own boundary
        already authorized the actor. Never call it from a page, router, or
        anything that renders.
        """
        credential = await self.repository.get_by_natural_key(randomizer, key)
        return credential.value if credential else None
