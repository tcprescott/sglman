"""Tenant Logo Service — a community's uploaded logo.

The logo replaces the coloured brand mark beside the wordmark and becomes the
browser tab icon, and can sit in black in the middle of the community's
equipment QR codes (chosen per print run). Uploads are never stored or served as
sent: a bitmap is decoded, checked and re-encoded into one square WebP, and an
SVG is rebuilt from an allowlist of drawing elements (``svg_sanitize``), so only
bytes this service produced ever leave the app. That closes SVG script,
metadata (EXIF/GPS) and appended-payload polyglots in one move.

Storage is the ``tenantlogo`` table (bytea), never the container filesystem.
``Tenant.config['logo']`` holds only the hash, so the page chrome builds the URL
from the tenant row it already loads. The URL embeds the hash, so it never
changes content and is cached for a year; a new upload is a new URL.
"""

import asyncio
import base64
import hashlib
import re
from collections import OrderedDict
from io import BytesIO
from typing import Optional

from PIL import Image, ImageOps, UnidentifiedImageError
from tortoise.transactions import in_transaction

from application.errors import require_found
from application.repositories.tenant_logo_repository import TenantLogoRepository
from application.repositories.tenant_repository import TenantRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.tenant_context import require_tenant_id
from application.utils.svg_sanitize import looks_like_svg, sanitise_svg
from models import User

MAX_UPLOAD_BYTES = 1024 * 1024
MAX_SOURCE_SIDE = 4096
MIN_SOURCE_SIDE = 64
OUTPUT_SIDE = 256
ALLOWED_FORMATS = frozenset({'PNG', 'JPEG', 'WEBP'})
ACCEPT = '.svg,.png,.jpg,.jpeg,.webp'

CONFIG_KEY = 'logo'
# 'svg' when the stored logo is a sanitised SVG; absent for the WebP.
FORMAT_KEY = 'logo_format'
_MIME = {'svg': 'image/svg+xml', 'webp': 'image/webp'}
ROUTE_PREFIX = '/brand-logo'
_SHA_RE = re.compile(r'^[0-9a-f]{64}$')
_TOO_BIG = f'Logos can be up to {MAX_SOURCE_SIDE}×{MAX_SOURCE_SIDE} pixels.'

# Keyed by (tenant_id, sha256). Entries never go stale because the key names
# the content, so the only policy needed is a size bound.
_CACHE_MAX = 128
_cache: 'OrderedDict[tuple[int, str], bytes]' = OrderedDict()


def logo_url(tenant_id: int, sha256: str, fmt: str = 'webp') -> str:
    return f'{ROUTE_PREFIX}/{tenant_id}/{sha256}.{fmt}'


def stored_format(content: bytes) -> str:
    """Which of the two formats this service stores ``content`` is."""
    return 'svg' if content.startswith(b'<svg') else 'webp'


def prepare_logo(data: bytes) -> tuple[bytes, str]:
    """Validate an upload and return ``(stored bytes, 'svg' | 'webp')``."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('Logos can be up to 1 MB. Try exporting a smaller file.')
    if data and looks_like_svg(data):
        return sanitise_svg(data), 'svg'
    return normalise_logo(data), 'webp'


def normalise_logo(data: bytes) -> bytes:
    """Validate an uploaded image and return it as a square ``OUTPUT_SIDE`` WebP.

    Raises ``ValueError`` with a message fit to show the uploader. The pixel
    bound is checked from the header before anything is decoded, which is what
    stops a small file that expands to gigabytes.
    """
    if not data:
        raise ValueError('That file is empty.')
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('Logos can be up to 1 MB. Try exporting a smaller PNG or WebP.')
    try:
        with Image.open(BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            probe.verify()
    except Image.DecompressionBombError:
        raise ValueError(_TOO_BIG) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ValueError("That file isn't an SVG, PNG, JPEG or WebP image.") from None
    if fmt not in ALLOWED_FORMATS:
        raise ValueError("That file isn't an SVG, PNG, JPEG or WebP image.")
    if max(width, height) > MAX_SOURCE_SIDE:
        raise ValueError(_TOO_BIG)
    if min(width, height) < MIN_SOURCE_SIDE:
        raise ValueError(f'Logos need to be at least {MIN_SOURCE_SIDE}×{MIN_SOURCE_SIDE} pixels.')

    try:
        with Image.open(BytesIO(data)) as img:
            img.load()
            upright = ImageOps.exif_transpose(img).convert('RGBA')
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ValueError("That image couldn't be read. Try saving it again as a PNG.") from None

    fitted = ImageOps.contain(upright, (OUTPUT_SIDE, OUTPUT_SIDE), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (OUTPUT_SIDE, OUTPUT_SIDE), (0, 0, 0, 0))
    canvas.paste(fitted, ((OUTPUT_SIDE - fitted.width) // 2, (OUTPUT_SIDE - fitted.height) // 2))
    out = BytesIO()
    canvas.save(out, 'WEBP', quality=90, method=6)
    return out.getvalue()


class TenantLogoService:
    """Upload, remove and serve a community's logo."""

    @staticmethod
    def logo_sha(config: Optional[dict]) -> Optional[str]:
        value = (config or {}).get(CONFIG_KEY)
        return value if isinstance(value, str) and _SHA_RE.match(value) else None

    @staticmethod
    def logo_format(config: Optional[dict]) -> str:
        return 'svg' if (config or {}).get(FORMAT_KEY) == 'svg' else 'webp'

    @staticmethod
    async def set_logo(actor: User, data: bytes) -> str:
        """Validate, normalise and store the current tenant's logo (STAFF only).

        Returns the new logo's URL.
        """
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            'Only Staff can change the community logo.',
        )
        tenant_id = require_tenant_id()
        # Decoding is CPU work; off the loop so one upload can't stall every page.
        content, fmt = await asyncio.to_thread(prepare_logo, data)
        sha256 = hashlib.sha256(content).hexdigest()

        async with in_transaction():
            tenant = require_found(await TenantRepository.get_by_id(tenant_id), 'Tenant')
            await TenantLogoRepository.upsert(content, sha256, actor)
            config = dict(tenant.config or {})
            config[CONFIG_KEY] = sha256
            if fmt == 'svg':
                config[FORMAT_KEY] = fmt
            else:
                config.pop(FORMAT_KEY, None)
            await TenantRepository.update(tenant, config=config)

        await AuditService().write_log(
            actor,
            AuditActions.THEME_LOGO_UPDATED,
            {'tenant_id': tenant_id, 'sha256': sha256, 'bytes': len(content), 'format': fmt},
        )
        return logo_url(tenant_id, sha256, fmt)

    @staticmethod
    async def remove_logo(actor: User) -> None:
        """Drop the current tenant's logo; the brand mark colour shows again."""
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            'Only Staff can change the community logo.',
        )
        tenant_id = require_tenant_id()
        async with in_transaction():
            tenant = require_found(await TenantRepository.get_by_id(tenant_id), 'Tenant')
            removed = await TenantLogoRepository.delete_current()
            config = dict(tenant.config or {})
            had_logo = config.pop(CONFIG_KEY, None) is not None
            config.pop(FORMAT_KEY, None)
            if had_logo:
                await TenantRepository.update(tenant, config=config)
        if removed or had_logo:
            await AuditService().write_log(
                actor, AuditActions.THEME_LOGO_REMOVED, {'tenant_id': tenant_id},
            )

    @staticmethod
    async def qr_logo_data_uri() -> Optional[str]:
        """The current community's logo as a ``data:`` URI for its QR codes.

        ``None`` when there is no logo. The URI is built only from bytes this
        service stored.
        """
        tenant_id = require_tenant_id()
        tenant = await TenantRepository.get_by_id(tenant_id)
        config = (tenant.config or {}) if tenant else {}
        sha256 = TenantLogoService.logo_sha(config)
        if sha256 is None:
            return None
        content = await TenantLogoService.get_logo_bytes(tenant_id, sha256)
        if content is None:
            return None
        mime = _MIME[stored_format(content)]
        return f'data:{mime};base64,{base64.b64encode(content).decode("ascii")}'

    @staticmethod
    async def get_logo_bytes(tenant_id: int, sha256: str) -> Optional[bytes]:
        """The stored WebP for this exact tenant and hash, else ``None``.

        Called from the public image route, with no community in scope.
        """
        if not _SHA_RE.match(sha256):
            return None
        key = (tenant_id, sha256)
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached
        content = await TenantLogoRepository.get_content(tenant_id, sha256)
        if content is None:
            return None
        _cache[key] = content
        if len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
        return content
