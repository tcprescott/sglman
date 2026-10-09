"""The one rule for a URL a person typed that the app later renders as a link.

A stored URL ends up in an ``<a href>`` (``ui.link``, a table slot, the static
bracket markup), and neither Vue nor the browser refuses ``javascript:`` there.
So every free-text URL field is limited to ``http(s)://`` where it is written,
and the renderers apply :func:`http_url_or_empty` again for rows written before
the rule existed.
"""

from typing import Optional

_ALLOWED_SCHEMES = ('http://', 'https://')


def is_http_url(value: Optional[str]) -> bool:
    return (value or '').strip().lower().startswith(_ALLOWED_SCHEMES)


def normalize_http_url(raw: Optional[str], label: str) -> Optional[str]:
    """``raw`` stripped, ``None`` when blank, or a ``ValueError`` naming ``label``."""
    text = (raw or '').strip()
    if not text:
        return None
    if not is_http_url(text):
        raise ValueError(f'{label} must start with http:// or https://.')
    return text


def http_url_or_empty(value: Optional[str]) -> str:
    """``value`` when it is an http(s) URL, else ``''`` so the link isn't drawn."""
    text = (value or '').strip()
    return text if is_http_url(text) else ''
