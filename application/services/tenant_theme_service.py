"""Tenant Theme Service — per-tenant brand colours over the shipped palette.

The app ships a fixed "Phoenix" palette (gold/ember) defined in ``theme/base.py``
and ``static/css/styles.css``. A community's STAFF may override a small set of
**brand** colours — primary, secondary, accent, and the header bar — which the
layout applies on top of the shipped defaults (Quasar colours + a handful of
``--sgl-*`` CSS variables). Semantic status colours (positive/negative/warning/
info) stay fixed so notifications and error states read consistently everywhere.

Storage is ``Tenant.config['theme']`` — no dedicated columns (see
``models/tenant.py``; the ``config`` JSONField is the documented home for
per-tenant knobs). Reads merge any stored overrides onto the defaults so a caller
always gets a full palette; writes are STAFF-gated, validated to 6-digit hex, and
audited. ``Tenant`` is the tenancy discriminator (never tenant-scoped), so this
service reads/writes through the cross-tenant ``TenantRepository``.
"""

import re
from typing import Optional

from application.errors import require_found
from application.repositories.tenant_repository import TenantRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.tenant_context import get_current_tenant_id, require_tenant_id
from models import User

# The overridable brand colours and their shipped Phoenix defaults. Keep these in
# sync with the ``:root`` seed values in static/css/styles.css and the fallback
# used by theme/base.py — ``primary`` mirrors --sgl-gold-deep, ``accent``
# --sgl-gold, ``secondary`` --sgl-ember-deep, ``header`` the light-mode
# --sgl-header-bg.
DEFAULT_THEME: dict[str, str] = {
    'primary': '#9C6B12',
    'secondary': '#C24E12',
    'accent': '#E0A82E',
    'header': '#9C6B12',
}
THEME_KEYS: tuple[str, ...] = tuple(DEFAULT_THEME.keys())

# Config sub-key under Tenant.config where the override dict lives.
CONFIG_KEY = 'theme'

_HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


class TenantThemeService:
    """Read/write a tenant's brand colour overrides."""

    @staticmethod
    def _merge(overrides: Optional[dict]) -> dict[str, str]:
        """Return a full palette: valid overrides layered onto the defaults."""
        colors = dict(DEFAULT_THEME)
        if overrides:
            for key in THEME_KEYS:
                value = overrides.get(key)
                if isinstance(value, str) and _HEX_RE.match(value):
                    colors[key] = value.lower()
        return colors

    @staticmethod
    async def get_theme(tenant_id: int) -> dict[str, str]:
        """The full brand palette for a tenant (overrides merged onto defaults)."""
        tenant = await TenantRepository.get_by_id(tenant_id)
        overrides = (tenant.config or {}).get(CONFIG_KEY) if tenant else None
        return TenantThemeService._merge(overrides)

    @staticmethod
    async def get_current_theme() -> dict[str, str]:
        """Best-effort palette for the in-scope tenant; defaults when none.

        Non-raising: the platform surface (no tenant) and the synchronous error
        page both fall back to the shipped Phoenix palette rather than turning a
        missing tenant into a chrome-render failure. Reads are always fresh
        (``get_by_id`` is uncached), so a saved change shows on the next load.
        """
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            return dict(DEFAULT_THEME)
        try:
            return await TenantThemeService.get_theme(tenant_id)
        except Exception:
            return dict(DEFAULT_THEME)

    @staticmethod
    def is_customized(colors: dict[str, str]) -> bool:
        """Whether a resolved palette differs from the shipped defaults."""
        return any(colors.get(key) != value for key, value in DEFAULT_THEME.items())

    @staticmethod
    async def set_theme(actor: User, colors: dict) -> dict[str, str]:
        """Validate and persist the current tenant's brand colours (STAFF only).

        A blank value for a key clears that override; clearing every key resets
        the tenant to the shipped palette. Returns the resulting full palette.
        """
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            'Only Staff can change theme colours.',
        )
        tenant_id = require_tenant_id()

        cleaned: dict[str, str] = {}
        for key in THEME_KEYS:
            raw = (colors.get(key) or '').strip()
            if not raw:
                continue
            if not _HEX_RE.match(raw):
                raise ValueError(
                    f'{key.title()} colour must be a 6-digit hex value like #9C6B12.'
                )
            cleaned[key] = raw.lower()

        tenant = require_found(await TenantRepository.get_by_id(tenant_id), 'Tenant')

        config = dict(tenant.config or {})
        if cleaned:
            config[CONFIG_KEY] = cleaned
        else:
            config.pop(CONFIG_KEY, None)
        await TenantRepository.update(tenant, config=config)

        await AuditService().write_log(
            actor,
            AuditActions.THEME_UPDATED,
            {'tenant_id': tenant_id, 'colors': cleaned},
        )
        return TenantThemeService._merge(cleaned)
