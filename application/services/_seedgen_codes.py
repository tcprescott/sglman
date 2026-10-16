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

# OoTR builds the seed after answering the create call (about 20s on the SGL
# preset). The wait sits inside the roll's 60s provider attempt, so it must stay
# well under it: a timed-out attempt is retried, and a retry mints a second seed.
OOTR_GENERATION_WAIT_SECONDS = 35
OOTR_STATUS_POLL_SECONDS = 2
OOTR_CODE_BUDGET_SECONDS = 45

# The page's Next.js payload sits inside a script string, so its quotes may
# arrive backslash-escaped.
_DASH_SIGNATURE = re.compile(r'\\?"signature\\?"\s*:\s*\\?"([A-Z][A-Z \-]{2,80})\\?"')
_OOTR_FILE_HASH = re.compile(r'\\?"file_hash\\?"\s*:\s*\[([^\]]{1,400})\]')
_OOTR_HASH_NAME = re.compile(r'\\?"([^"\\]{1,40})\\?"')


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


def dash_code_from_page(html: str) -> Optional[list[str]]:
    """DASH has no seed API; its seed page embeds the signature in its data."""
    found = _DASH_SIGNATURE.search(html or '')
    return _words(found.group(1)) if found else None


def ootr_code_from_page(html: str) -> Optional[list[str]]:
    """The seed page embeds its settings log as an escaped JS string."""
    found = _OOTR_FILE_HASH.search(html or '')
    if not found:
        return None
    names = _OOTR_HASH_NAME.findall(found.group(1))
    return names if 0 < len(names) <= 8 else None


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
    """Wait for the seed to finish generating, then read the code off its page.

    The SGL key only opens ``/api/sglive/``, whose details endpoint leaves out the
    settings log, so the public seed page is the one place the code is served.
    Scraping it can break whenever OoTR changes that page, so every miss logs at
    ERROR (a Sentry issue) and the roll goes ahead without a code.
    """
    try:
        async with asyncio.timeout(OOTR_CODE_BUDGET_SECONDS):
            if not await _ootr_generated(seed_id, api_key):
                return None
            timeout = aiohttp.ClientTimeout(total=CODE_FETCH_TIMEOUT_SECONDS)
            async with aiohttp.request(
                method='get', url='https://ootrandomizer.com/seed/get',
                params={'id': seed_id}, timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    logger.error('OoTR seed code unavailable for %s: seed page HTTP %s', seed_id, resp.status)
                    return None
                code = ootr_code_from_page(await resp.text())
    except Exception as e:
        # Broad on purpose: a scraper that breaks must cost the code, never the roll.
        logger.error('OoTR seed code unavailable for %s: %r', seed_id, e, exc_info=True)
        return None
    if code is None:
        logger.error('OoTR seed code unavailable for %s: no file_hash on the seed page', seed_id)
    return code


async def _ootr_generated(seed_id: str, api_key: str) -> bool:
    """Poll ``/api/sglive/seed/status`` until the seed is built (status 1)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + OOTR_GENERATION_WAIT_SECONDS
    timeout = aiohttp.ClientTimeout(total=CODE_FETCH_TIMEOUT_SECONDS)
    while True:
        async with aiohttp.request(
            method='get', url='https://ootrandomizer.com/api/sglive/seed/status',
            params={'id': seed_id, 'key': api_key}, timeout=timeout,
        ) as resp:
            body = await resp.json(content_type=None) if resp.status == 200 else None
        status = body.get('status') if isinstance(body, dict) else None
        if status == 1:
            return True
        if status not in (0, None) or resp.status not in (200, 204):
            logger.error('OoTR seed code unavailable for %s: status HTTP %s, %r', seed_id, resp.status, body)
            return False
        if loop.time() + OOTR_STATUS_POLL_SECONDS > deadline:
            logger.error(
                'OoTR seed code unavailable for %s: still generating after %ss',
                seed_id, OOTR_GENERATION_WAIT_SECONDS,
            )
            return False
        await asyncio.sleep(OOTR_STATUS_POLL_SECONDS)


_MOCK_ENEMIES = ('GEEMER', 'RIPPER', 'VIOLA', 'WAVER', 'SOVA', 'ZOA', 'BULL', 'SKREE')


def mock_code(randomizer: str) -> Optional[list[str]]:
    """A believable code for ``MOCK_SEEDGEN``, so dev shows the line."""
    if randomizer in ('alttpr', 'ootr'):
        return random.choices(ALTTPR_CODE_NAMES, k=5)
    if randomizer in ('smmap', 'smdash'):
        return random.choices(_MOCK_ENEMIES, k=4)
    return None
