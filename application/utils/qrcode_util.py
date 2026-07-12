"""QR code generation for equipment assets.

Each asset's QR code encodes the absolute URL of its detail page so that
scanning it jumps straight there (login required). Callers pass the fully-built
URL — in path mode that is tenant-qualified (``/t/<slug>/equipment/<id>``), so
the util itself stays tenant-agnostic.
"""

import base64
from io import BytesIO

import qrcode


def asset_qr_png_bytes(url: str) -> bytes:
    """Render a QR code for ``url`` as PNG bytes."""
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def asset_qr_data_uri(url: str) -> str:
    """Render a QR code for ``url`` as a ``data:image/png;base64`` URI for inline display."""
    b64 = base64.b64encode(asset_qr_png_bytes(url)).decode('ascii')
    return f"data:image/png;base64,{b64}"
