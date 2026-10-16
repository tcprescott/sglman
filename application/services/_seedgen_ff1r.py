"""Final Fantasy Randomizer presets: the flags link a preset holds, checked.

FFR has no API. A preset is the link copied from the randomizer's address bar,
and each roll swaps a fresh seed into it (``SeedGenerationService._generate_ff1r``).
"""

import urllib.parse
from typing import Optional

FF1R_HOST = 'finalfantasyrandomizer.com'


def ff1r_reference_url(settings: Optional[dict]) -> str:
    """The FFR flags link a preset holds, checked, or ``ValueError`` naming what's wrong."""
    settings = settings if isinstance(settings, dict) else {}
    url = settings.get('url')
    if not isinstance(url, str) or not url.strip():
        raise ValueError('A Final Fantasy preset needs a "url": the flags link copied from finalfantasyrandomizer.com.')
    unknown = set(settings) - {'url'}
    if unknown:
        raise ValueError(f"A Final Fantasy preset holds only a flags link, not {', '.join(sorted(unknown))}.")
    url = url.strip()
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not (host == FF1R_HOST or host.endswith('.' + FF1R_HOST)):
        raise ValueError('That isn\'t a finalfantasyrandomizer.com link. Copy the link from the site\'s address bar.')
    if not urllib.parse.parse_qs(parsed.query).get('f', [''])[0]:
        raise ValueError('That link has no flags in it (the "f=" part). Copy it again after setting the flags.')
    return url
