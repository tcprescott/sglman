"""Dev seed: a community logo, so the header and tab icon show the logo path.

The image is drawn here rather than shipped, then passed through the same
``normalise_logo`` an upload goes through, so the stored bytes are exactly what
production would store.
"""

import hashlib
from io import BytesIO

from PIL import Image, ImageDraw

from application.services.tenant_logo_service import CONFIG_KEY, normalise_logo
from models import Tenant, TenantLogo


def _draw_logo() -> bytes:
    img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((16, 16, 496, 496), fill=(14, 116, 112, 255))
    draw.polygon([(256, 96), (416, 384), (96, 384)], fill=(255, 255, 255, 255))
    draw.polygon([(256, 224), (336, 384), (176, 384)], fill=(14, 116, 112, 255))
    out = BytesIO()
    img.save(out, 'PNG')
    return out.getvalue()


async def seed_logo_for_tenant(tenant: Tenant) -> None:
    """Give ``tenant`` a logo unless it already has one (a dev's own upload stays)."""
    if await TenantLogo.exists(tenant_id=tenant.id):
        return
    content = normalise_logo(_draw_logo())
    sha256 = hashlib.sha256(content).hexdigest()
    await TenantLogo.create(tenant=tenant, content=content, sha256=sha256)
    config = dict(tenant.config or {})
    config[CONFIG_KEY] = sha256
    tenant.config = config
    await tenant.save()
    print(f"    [{tenant.slug}] logo ok")
