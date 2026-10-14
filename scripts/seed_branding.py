"""Dev seed: a community logo, so the header, tab icon and QR codes show the logo path.

The logo is an SVG written here rather than shipped, then passed through the
same ``prepare_logo`` an upload goes through, so the stored bytes are exactly
what production would store. It is wider than it is tall, like most real
wordmark logos, so the header and QR tile show how a non-square mark fits.
"""

import hashlib

from application.services.tenant_logo_service import CONFIG_KEY, FORMAT_KEY, prepare_logo
from models import Tenant, TenantLogo

_LOGO_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">
  <style>.mark { fill: #0e7470; }</style>
  <ellipse class="mark" cx="320" cy="240" rx="304" ry="224"/>
  <polygon fill="#fff" points="320 72 488 392 152 392"/>
  <polygon class="mark" points="320 216 404 392 236 392"/>
</svg>"""


async def seed_logo_for_tenant(tenant: Tenant) -> None:
    """Give ``tenant`` a logo unless it already has one (a dev's own upload stays)."""
    if await TenantLogo.exists(tenant_id=tenant.id):
        return
    content, fmt = prepare_logo(_LOGO_SVG)
    sha256 = hashlib.sha256(content).hexdigest()
    await TenantLogo.create(tenant=tenant, content=content, sha256=sha256)
    config = dict(tenant.config or {})
    config[CONFIG_KEY] = sha256
    config[FORMAT_KEY] = fmt
    tenant.config = config
    await tenant.save()
    print(f"    [{tenant.slug}] logo ok")
