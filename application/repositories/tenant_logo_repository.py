"""Tenant Logo Repository - Data Access Layer

The one-row-per-community store for the uploaded logo (see ``models.TenantLogo``).
"""

from typing import Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import TenantLogo, User


class TenantLogoRepository(TenantScopedRepository[TenantLogo]):
    model = TenantLogo

    @staticmethod
    async def get_content(tenant_id: int, sha256: str) -> Optional[bytes]:
        """The image bytes for an exact tenant + hash, else ``None``.

        Cross-tenant by design: the image route runs at the site root with no
        community bound, so the tenant comes from the URL. The logo is public
        (it sits on signed-out pages), and the hash must match too, so a guessed
        id alone returns nothing.
        """
        rows = await scoped(TenantLogo.filter(sha256=sha256), tenant_id).values_list('content', flat=True)
        return bytes(rows[0]) if rows else None

    @staticmethod
    async def upsert(content: bytes, sha256: str, uploaded_by: User) -> TenantLogo:
        logo, _ = await TenantLogo.update_or_create(
            tenant_id=current_tenant_id(),
            defaults={'content': content, 'sha256': sha256, 'uploaded_by': uploaded_by},
        )
        return logo

    @staticmethod
    async def delete_current() -> int:
        return await scoped(TenantLogo.all()).delete()
