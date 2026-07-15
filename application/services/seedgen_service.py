"""
Seed Generation Service - Business Logic Layer

Handles random seed generation for various randomizers.
Supports: ALTTPR, FF1R, Z1R, SMMAP, OOTR, and Test.
Registers not-yet-implemented stubs: MMR, SMDASH, DK64R, WWR.
"""

import asyncio
import json
import os
import random
import secrets
import urllib.parse
from typing import Optional

import aiohttp
import yaml
from pyz3r import ALTTPR

from application.tenant_context import require_tenant_id
from application.utils.mock_seedgen import is_mock_seedgen
from models import Preset


class SeedGenerationService:
    """Service for generating seeds for various randomizers."""

    # Available randomizers
    AVAILABLE_RANDOMIZERS = [
        'alttpr',
        'ff1r',
        'z1r',
        'smmap',
        'ootr',
        'mmr',
        'smdash',
        'dk64r',
        'wwr',
        'test',
    ]

    # Randomizers registered for selection but whose generator is not yet
    # wired to an upstream API — rolling one raises ``NotImplementedError``.
    STUB_RANDOMIZERS = {'mmr', 'smdash', 'dk64r', 'wwr'}

    # Randomizers whose generator can embed community triforce texts.
    TRIFORCE_TEXT_RANDOMIZERS = {'alttpr'}

    @classmethod
    def supports_triforce_texts(cls, generator: Optional[str]) -> bool:
        return generator in cls.TRIFORCE_TEXT_RANDOMIZERS

    async def generate_seed(self, randomizer: str, preset: Optional[Preset] = None) -> str:
        """
        Generate a seed for the specified randomizer.

        Args:
            randomizer: Name of the randomizer (alttpr, ff1r, z1r, smmap, ootr, test)
            preset: Optional resolved ``Preset`` supplying the randomizer settings.
                ALTTPR uses ``preset.settings`` when given; without a preset it
                falls back to the built-in ``casualboots`` settings. Other
                backends are still hard-coded until PR 11 and ignore the preset.

        Returns:
            URL or string representing the generated seed

        Raises:
            ValueError: If randomizer is not supported
        """
        generator_map = {
            'alttpr': self._generate_alttpr,
            'ff1r': self._generate_ff1r,
            'z1r': self._generate_z1r,
            'smmap': self._generate_smmap,
            'ootr': self._generate_ootr,
            'mmr': self._generate_mmr,
            'smdash': self._generate_smdash,
            'dk64r': self._generate_dk64r,
            'wwr': self._generate_wwr,
            'test': self._generate_test,
        }

        if randomizer not in generator_map:
            raise ValueError(f"Unsupported randomizer: {randomizer}")

        if is_mock_seedgen():
            return self._mock_seed_url(randomizer)

        if randomizer == 'alttpr':
            return await self._generate_alttpr(preset)
        return await generator_map[randomizer]()

    @staticmethod
    def _mock_seed_url(randomizer: str) -> str:
        """A believable, unique permalink for MOCK_SEEDGEN mode."""
        return f"https://mock.seedgen.local/{randomizer}/{secrets.token_hex(8)}"

    async def _generate_alttpr(self, preset: Optional[Preset] = None) -> str:
        """
        Generate an A Link to the Past Randomizer seed.

        Uses ``preset.settings`` when a preset is supplied; otherwise falls back
        to the built-in ``casualboots`` settings (the historical default).

        Returns:
            URL to the generated seed
        """
        if preset is not None:
            settings = preset.settings
        else:
            with open("presets/alttpr/casualboots.yaml", "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f)['settings']

        seed = await ALTTPR.generate(
            settings=settings,
            endpoint='/api/customizer',
        )
        return seed.url

    async def generate_alttpr_for_tournament(
        self,
        tournament_id: int,
        balanced: bool = True,
    ) -> str:
        """Generate an ALTTPR seed with a community triforce text embedded.

        Selects an approved text from the tournament's pool (balanced by
        default so every submitter is weighted equally). Falls back to a
        plain seed when no approved texts exist.
        """
        from application.services.triforce_text_service import TriforceTextService
        from models import Tournament

        tournament = await Tournament.get_or_none(id=tournament_id, tenant_id=require_tenant_id())
        if tournament is None:
            raise ValueError(f"Tournament {tournament_id} not found.")

        with open("presets/alttpr/casualboots.yaml", "r", encoding="utf-8") as f:
            preset = yaml.safe_load(f)

        service = TriforceTextService()
        text = (
            await service.get_balanced_text(tournament)
            if balanced
            else await service.get_random_text(tournament)
        )
        if text:
            preset.setdefault('settings', {}).setdefault('texts', {})
            preset['settings']['texts']['end_triforce'] = "{NOBORDER}\n" + text

        seed = await ALTTPR.generate(
            settings=preset['settings'],
            endpoint='/api/customizer',
        )
        return seed.url
    
    async def _generate_ff1r(self) -> str:
        """
        Generate a Final Fantasy 1 Randomizer seed.
        
        Returns:
            URL to the generated seed
        """
        url = 'https://4-8-6.finalfantasyrandomizer.com/?s=00000000&f=6XOcCG.geJ.YDwt9.jijRao2NoTvBlq0V2VvHuAxjtMhlVRYso0wmNtUopSO9Xzt2k8Gn7v9d6ysABeksoaTevatcw4ZKZoMV95h1NQISZlbvlK8FEwtAAT5KWQUztLnkzQuDcO36uLraMFFQpGq0YsZrZHr7YdUoUxsW5.IutAsHfjB'
        seed = ('%008x' % random.randrange(16 ** 8)).upper()
        up = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(up.query)
        qs['s'] = seed
        newurl = urllib.parse.urlunparse((up.scheme, up.netloc, up.path, up.params,
                                          urllib.parse.urlencode(qs, doseq=True), up.fragment))
        return newurl
    
    async def _generate_z1r(self) -> str:
        """
        Generate a Zelda 1 Randomizer seed.
        
        Returns:
            String with seed number and flags
        """
        flags = '5K!ELDXj35eUlQNR4XAhcL18nJBPgbC4Hpw'
        seed = random.randint(0, 8999999999999999999)
        return f"{seed} - {flags}"
    
    async def _generate_smmap(self) -> str:
        """
        Generate a Super Metroid Map Randomizer seed.
        
        Returns:
            URL to the generated seed
        """
        # Never fall back to a committed default — a leaked spoiler token
        # unlocks spoiler logs for race seeds (mirrors the OOTR_API_KEY guard).
        spoiler_token = os.environ.get('SMMAP_SPOILER_TOKEN')
        if not spoiler_token:
            raise ValueError('SMMAP_SPOILER_TOKEN is not configured.')
        with open("presets/smmap/community_race_s4.json", "r", encoding="utf-8") as f:
            settings = f.read()

        async with aiohttp.ClientSession() as session:
            with aiohttp.MultipartWriter('form-data') as mpwriter:
                mpwriter.append(spoiler_token).set_content_disposition('form-data', name='spoiler_token')
                mpwriter.append(settings).set_content_disposition('form-data', name='settings')
            async with session.post('https://maprando.com/randomize', data=mpwriter) as resp:
                data = await resp.json()

        return f"https://maprando.com{data['seed_url']}"
    
    async def _generate_ootr(self) -> str:
        """
        Generate an Ocarina of Time Randomizer seed.
        
        Returns:
            URL to the generated seed
        """
        with open("presets/ootr/sgl25.json", "r", encoding="utf-8") as f:
            settings = json.load(f)

        # The OOTR API authenticates via a ``key`` query parameter; guard
        # against silently sending key=None when it is not configured.
        api_key = os.environ.get('OOTR_API_KEY')
        if not api_key:
            raise ValueError('OOTR_API_KEY is not configured.')

        async with aiohttp.request(
            method='post',
            url="https://ootrandomizer.com/api/sglive/seed/create",
            raise_for_status=True,
            json=settings,
            params={
                "key": api_key,
                "version": "8.3.0",
                "encrypt": "true"
            }
        ) as resp:
            result = await resp.json()

        return f"https://ootrandomizer.com/seed/get?id={result['id']}"
    
    async def _generate_mmr(self) -> str:
        """Generate a Majora's Mask Randomizer seed. Not yet implemented."""
        raise NotImplementedError("Majora's Mask Randomizer seed generation is not yet implemented.")

    async def _generate_smdash(self) -> str:
        """Generate a Super Metroid: DASH seed. Not yet implemented."""
        raise NotImplementedError("Super Metroid: DASH seed generation is not yet implemented.")

    async def _generate_dk64r(self) -> str:
        """Generate a Donkey Kong 64 Randomizer seed. Not yet implemented."""
        raise NotImplementedError("Donkey Kong 64 Randomizer seed generation is not yet implemented.")

    async def _generate_wwr(self) -> str:
        """Generate a Wind Waker Randomizer seed. Not yet implemented."""
        raise NotImplementedError("Wind Waker Randomizer seed generation is not yet implemented.")

    async def _generate_test(self) -> str:
        """
        Generate a test seed (for testing purposes).
        
        Returns:
            URL to a test seed
        """
        await asyncio.sleep(5)  # Simulate processing time
        return "https://example.com/test-seed-url"
