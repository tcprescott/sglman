# we will need random seed generation for
# 1. ALTTPR
# 2. FF1R
# 3. Z1R
# 4. MMR
# 5. OOTR

from pyz3r import ALTTPR
import yaml
import random
import urllib.parse
import aiohttp
import json
import os
import asyncio


async def generate_alttpr() -> None:
    with open("presets/alttpr/casualboots.yaml", "r") as f:
            preset = yaml.safe_load(f)

    seed = await ALTTPR.generate(
        settings=preset['settings'],
        endpoint='/api/customizer',
    )
    return seed.url

async def generate_ff1r() -> None:
    url = 'https://4-8-6.finalfantasyrandomizer.com/?s=47D73892&f=w5YDdiKkqjtl1K6HiZNJrspHlS20-jLRBJ1SSNZiBJvybkMw1.dWcvHnfFfp.zkPTB90SuAl2vX04hO8F5ApVp1XVza-V-DBIfVS5ptlLkw9iH4vi19U0OSe0ZpjeDmJUH4g2YFJYiMk2plLvWjbCIH4p0-Ccq7LHUQH.q.IutAsHfjB'
    seed = ('%008x' % random.randrange(16 ** 8)).upper()
    up = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(up.query)
    qs['s'] = seed
    newurl = urllib.parse.urlunparse((up.scheme, up.netloc, up.path, up.params,
                                      urllib.parse.urlencode(qs, doseq=True), up.fragment))
    return newurl


async def generate_z1r() -> None:
    flags = '5K!ELDXj35eUlQNR4XAhcL18nJBPgbC4Hpw'
    seed = random.randint(0, 8999999999999999999)
    return f"{seed} - {flags}"

async def generate_smmap() -> None:
    spoiler_token = 'SpeedGamingLive2025IsTheBestTournamentEverAndEverLOL'
    with open("presets/smmap/community_race_s4.json", "r") as f:
        settings = f.read()

    async with aiohttp.ClientSession() as session:
        with aiohttp.MultipartWriter('form-data') as mpwriter:
            mpwriter.append(spoiler_token).set_content_disposition('form-data', name='spoiler_token')
            mpwriter.append(settings).set_content_disposition('form-data', name='settings')
        async with session.post('https://maprando.com/randomize', data=mpwriter) as resp:
            data = await resp.json()

    return f"https://maprando.com{data['seed_url']}"

async def generate_mmr() -> None:
    return "https://example.com/mmr-seed-url"

async def generate_ootr() -> None:
    with open("presets/ootr/sgl25.json", "r") as f:
        settings = json.load(f)
    async with aiohttp.request(
        method='post',
        url="https://ootrandomizer.com/api/sglive/seed/create",
        raise_for_status=True,
        json=settings,
        params={
            "key": os.environ.get('OOTR_API_KEY'),
            "version": "8.3.0",
            "encrypt": "true"
        }
    ) as resp:
        result = await resp.json()

    return f"https://ootrandomizer.com/seed/get?id={result['id']}"

async def generate_wwr() -> None:
    return "https://example.com/wwr-seed-url"

async def generate_test() -> None:
    await asyncio.sleep(5) # simulate processing time
    return "https://example.com/test-seed-url"

# map of randomizers to their generation functions
RANDOMIZERS = {
    'alttpr': generate_alttpr,
    'ff1r': generate_ff1r,
    'z1r': generate_z1r,
    'smmap': generate_smmap,
    # 'mmr': generate_mmr,
    'ootr': generate_ootr,
    # 'wwr': generate_wwr,
    'test': generate_test,
}