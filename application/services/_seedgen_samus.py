"""The samus.link backends: Super Metroid (sm.samus.link) and SMZ3 (samus.link).

Both sites run the same randomizer service: POST a settings object to
``/api/randomizers/<id>/generate`` and get back the seed's guid and its
four-word hash. The seed page lives at ``/seed/<slug>``, the slug being the
guid's URL-safe base64. A ``Preset`` holds the settings object the site's own
form sends; every roll is forced to a race seed with no spoiler key.
"""

import base64
import copy
import uuid
from typing import Optional

import aiohttp

import application.services._seedgen_codes as seed_codes
from application.services._seedgen_types import RolledSeed
from application.utils.seed_provider import (
    SeedProviderBadResponse,
    SeedProviderInvalidRequest,
    raise_for_status,
)

SAMUS_SITES = {
    'sm': ('https://sm.samus.link', 'Super Metroid'),
    'smz3': ('https://samus.link', 'SMZ3'),
}

# Keys a roll owns: a stored seed number would repeat a seed, and a spoiler key
# would let anyone holding it read a race seed's spoiler.
_ROLL_OWNED_KEYS = {'seed', 'race', 'spoilerKey'}


def samus_settings(randomizer: str, settings: Optional[dict]) -> dict:
    """A preset's samus.link settings, checked, or ``ValueError``."""
    label = SAMUS_SITES[randomizer][1]
    if not isinstance(settings, dict) or not settings:
        raise ValueError(f'{label} needs a preset with the randomizer settings. Add one on the Presets tab.')
    if not all(isinstance(k, str) and isinstance(v, (str, int, bool)) for k, v in settings.items()):
        raise ValueError(f'{label} settings are one flat object of setting names to values.')
    return {k: v for k, v in settings.items() if k not in _ROLL_OWNED_KEYS}


def _slug(guid: str) -> str:
    return base64.urlsafe_b64encode(uuid.UUID(hex=guid).bytes).rstrip(b'=').decode('ascii')


async def generate_samus(randomizer: str, settings: Optional[dict]) -> RolledSeed:
    """Roll one race seed on sm.samus.link or samus.link."""
    try:
        payload = copy.deepcopy(samus_settings(randomizer, settings))
    except ValueError as e:
        raise SeedProviderInvalidRequest(str(e), provider=randomizer, operation='generate_seed') from None
    payload.update({'seed': '', 'race': 'true'})
    base_url = SAMUS_SITES[randomizer][0]

    async with aiohttp.request(
        method='post', url=f'{base_url}/api/randomizers/{randomizer}/generate', json=payload,
    ) as resp:
        await raise_for_status(resp, provider=randomizer, operation='generate_seed')
        data = await resp.json(content_type=None)

    guid = data.get('guid') if isinstance(data, dict) else None
    try:
        if not isinstance(guid, str):
            raise ValueError('no guid')
        slug = _slug(guid)
    except ValueError:
        raise SeedProviderBadResponse(
            f'{SAMUS_SITES[randomizer][1]} returned no seed id.',
            provider=randomizer, operation='generate_seed',
        ) from None
    return RolledSeed(
        url=f'{base_url}/seed/{slug}', settings=payload,
        code=seed_codes.samus_code(data.get('hash')),
    )
