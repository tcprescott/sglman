"""QR code generation for equipment assets.

Each asset's QR code encodes the absolute URL of its detail page so that
scanning it jumps straight to ``/equipment/{asset_id}`` (login required).
"""

import base64
from io import BytesIO

import qrcode

from application.utils.environment import get_base_url


def asset_url(asset_id: int) -> str:
    return f"{get_base_url()}/equipment/{asset_id}"


def asset_qr_png_bytes(asset_id: int) -> bytes:
    """Render the asset's QR code as PNG bytes."""
    img = qrcode.make(asset_url(asset_id))
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def asset_qr_data_uri(asset_id: int) -> str:
    """Render the asset's QR code as a ``data:image/png;base64`` URI for inline display."""
    b64 = base64.b64encode(asset_qr_png_bytes(asset_id)).decode('ascii')
    return f"data:image/png;base64,{b64}"
