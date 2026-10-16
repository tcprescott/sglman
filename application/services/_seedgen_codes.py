"""Seed codes: the symbols a game shows on its file select so racers can check
they are playing the same seed.

Only randomizers whose upstream hands the code back are covered. The rest work
it out on the player's machine (FFR, Z1R) or from a secret baked into official
builds (WWR), so a code computed here would disagree with the players' screens,
and showing a wrong code is worse than showing none. Every reader here returns
``None`` rather than raising: a missing code must never fail or retry a roll,
because each retry mints a new, publicly-numbered seed upstream.
"""

import asyncio
import logging
import random
import re
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# The order is the game's: index n in the ROM is the nth name.
ALTTPR_CODE_NAMES = (
    'Bow', 'Boomerang', 'Hookshot', 'Bombs', 'Mushroom', 'Magic Powder', 'Ice Rod',
    'Pendant', 'Bombos', 'Ether', 'Quake', 'Lamp', 'Hammer', 'Shovel', 'Flute',
    'Bugnet', 'Book', 'Empty Bottle', 'Green Potion', 'Somaria', 'Cape', 'Mirror',
    'Boots', 'Gloves', 'Flippers', 'Moon Pearl', 'Shield', 'Tunic', 'Heart', 'Map',
    'Compass', 'Big Key',
)
_ALTTPR_CODE_OFFSET = 0x180215

# DK64R's own racetime bot names its 0-9 hash digits this way.
DK64R_CODE_NAMES = (
    'Bongos', 'Crown', 'DK Coin', 'Fairy', 'Guitar', 'Nintendo Coin', 'Orange',
    'Rainbow Coin', 'Rareware Coin', 'Saxophone',
)

CODE_FETCH_TIMEOUT_SECONDS = 8

# The page's Next.js payload sits inside a script string, so its quotes may
# arrive backslash-escaped.
_DASH_SIGNATURE = re.compile(r'\\?"signature\\?"\s*:\s*\\?"([A-Z][A-Z \-]{2,80})\\?"')


def _words(value) -> Optional[list[str]]:
    if not isinstance(value, str):
        return None
    words = value.split()
    return words if 2 <= len(words) <= 8 else None


def alttpr_code(patch) -> Optional[list[str]]:
    """The five file-select items, read from the patch alttpr.com returned.

    The patch is a list of ``{offset: [bytes]}`` writes; the code is the five
    bytes at ``0x180215``, inside whichever write covers that address.
    """
    if not isinstance(patch, list):
        return None
    for write in patch:
        if not isinstance(write, dict):
            continue
        for start, data in write.items():
            try:
                rel = _ALTTPR_CODE_OFFSET - int(start)
            except (TypeError, ValueError):
                continue
            if isinstance(data, list) and 0 <= rel and rel + 5 <= len(data):
                raw = data[rel:rel + 5]
                if all(isinstance(b, int) and 0 <= b < len(ALTTPR_CODE_NAMES) for b in raw):
                    return [ALTTPR_CODE_NAMES[b] for b in raw]
                return None
    return None


def dk64r_code(digits) -> Optional[list[str]]:
    if not isinstance(digits, list) or not digits:
        return None
    if not all(isinstance(d, int) and 0 <= d < len(DK64R_CODE_NAMES) for d in digits):
        return None
    return [DK64R_CODE_NAMES[d] for d in digits]


def smmap_code(seed_hash) -> Optional[list[str]]:
    """Map Rando's four enemy names, sent beside ``seed_url`` as one string."""
    return _words(seed_hash)


def samus_code(seed_hash) -> Optional[list[str]]:
    """samus.link's four enemy names (Super Metroid and SMZ3), sent as one string."""
    return _words(seed_hash)


# Door rando builds name some items more briefly than the game's own list.
_AVIANART_SHORT_NAMES = {
    'Bomb': 'Bombs', 'Powder': 'Magic Powder', 'Rod': 'Ice Rod', 'Ocarina': 'Flute',
    'Bug Net': 'Bugnet', 'Bottle': 'Empty Bottle', 'Potion': 'Green Potion',
    'Cane': 'Somaria', 'Pearl': 'Moon Pearl', 'Key': 'Big Key',
}


def avianart_code(result) -> Optional[list[str]]:
    """AVIANART's five file-select items, a comma-separated string.

    Plain ALTTPR presets send it as ``fshash``; door rando presets leave that out
    and put it in ``spoiler.meta.hash`` with the shorter names above.
    """
    if not isinstance(result, dict):
        return None
    value = result.get('fshash')
    if not value:
        spoiler = result.get('spoiler')
        meta = spoiler.get('meta') if isinstance(spoiler, dict) else None
        value = meta.get('hash') if isinstance(meta, dict) else None
    if not isinstance(value, str):
        return None
    names = [_AVIANART_SHORT_NAMES.get(n.strip(), n.strip()) for n in value.split(',')]
    if len(names) != 5 or not all(names) or any(len(n) > 40 for n in names):
        return None
    return names


def dash_code_from_page(html: str) -> Optional[list[str]]:
    """DASH has no seed API; its seed page embeds the signature in its data."""
    found = _DASH_SIGNATURE.search(html or '')
    return _words(found.group(1)) if found else None


def ootr_code(details) -> Optional[list[str]]:
    log = (details or {}).get('settingsLog') if isinstance(details, dict) else None
    hashes = log.get('file_hash') if isinstance(log, dict) else None
    if not isinstance(hashes, list) or not hashes:
        return None
    if not all(isinstance(h, str) and 0 < len(h) <= 40 for h in hashes):
        return None
    return list(hashes)


async def fetch_dash_code(seed_url: str) -> Optional[list[str]]:
    try:
        timeout = aiohttp.ClientTimeout(total=CODE_FETCH_TIMEOUT_SECONDS)
        async with aiohttp.request(method='get', url=seed_url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return dash_code_from_page(await resp.text())
    except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError) as e:
        logger.info('DASH seed code unavailable for %s: %s', seed_url, e)
        return None


async def fetch_ootr_code(seed_id: str, api_key: str) -> Optional[list[str]]:
    """Read the code from the seed's settings log.

    OoTR only serves the log for an encrypted seed to a key with its
    ``locked_encrypt_spoiler_access`` scope, and answers 204 while the seed is
    still generating; either way the roll goes ahead without a code.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=CODE_FETCH_TIMEOUT_SECONDS)
        async with aiohttp.request(
            method='get', url='https://ootrandomizer.com/api/v2/seed/details',
            params={'id': seed_id, 'key': api_key}, timeout=timeout,
        ) as resp:
            if resp.status != 200:
                logger.info('OoTR seed code unavailable for %s: HTTP %s', seed_id, resp.status)
                return None
            return ootr_code(await resp.json(content_type=None))
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
        logger.info('OoTR seed code unavailable for %s: %s', seed_id, e)
        return None


_MOCK_ENEMIES = ('GEEMER', 'RIPPER', 'VIOLA', 'WAVER', 'SOVA', 'ZOA', 'BULL', 'SKREE')


def mock_code(randomizer: str) -> Optional[list[str]]:
    """A believable code for ``MOCK_SEEDGEN``, so dev shows the line."""
    if randomizer in ('alttpr', 'alttprdr', 'ootr', 'avianart'):
        return random.choices(ALTTPR_CODE_NAMES, k=5)
    if randomizer in ('smmap', 'smdash', 'sm', 'smz3'):
        return random.choices(_MOCK_ENEMIES, k=4)
    return None
