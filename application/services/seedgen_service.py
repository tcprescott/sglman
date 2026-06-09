"""
Seed Generation Service - Business Logic Layer

Handles random seed generation for various randomizers.
Supports: ALTTPR, FF1R, Z1R, SMMAP, OOTR, MMR, WWR, and Test.
"""

import asyncio
import json
import os
import random
import urllib.parse

import aiohttp
import yaml
from pyz3r import ALTTPR


class SeedGenerationService:
    """Service for generating seeds for various randomizers."""
    
    # Available randomizers
    AVAILABLE_RANDOMIZERS = [
        'alttpr',
        'ff1r',
        'z1r',
        'smmap',
        'ootr',
        'test',
    ]
    
    async def generate_seed(self, randomizer: str) -> str:
        """
        Generate a seed for the specified randomizer.
        
        Args:
            randomizer: Name of the randomizer (alttpr, ff1r, z1r, smmap, ootr, test)
            
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
            'test': self._generate_test,
        }
        
        if randomizer not in generator_map:
            raise ValueError(f"Unsupported randomizer: {randomizer}")
        
        return await generator_map[randomizer]()
    
    async def _generate_alttpr(self) -> str:
        """
        Generate an A Link to the Past Randomizer seed.

        Returns:
            URL to the generated seed
        """
        with open("presets/alttpr/casualboots.yaml", "r", encoding="utf-8") as f:
            preset = yaml.safe_load(f)

        seed = await ALTTPR.generate(
            settings=preset['settings'],
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

        tournament = await Tournament.get_or_none(id=tournament_id)
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
        spoiler_token = os.environ.get(
            'SMMAP_SPOILER_TOKEN',
            'SpeedGamingLive2025IsTheBestTournamentEverAndEverLOL',
        )
        with open("presets/smmap/community_race_s4.json", "r", encoding="utf-8") as f:
            settings = f.read()

        async with aiohttp.ClientSession() as session:
            with aiohttp.MultipartWriter('form-data') as mpwriter:
                mpwriter.append(spoiler_token).set_content_disposition('form-data', name='spoiler_token')
                mpwriter.append(settings).set_content_disposition('form-data', name='settings')
            async with session.post('https://maprando.com/randomize', data=mpwriter) as resp:
                data = await resp.json()

        return f"https://maprando.com{data['seed_url']}"
    
    async def _generate_mmr(self) -> str:
        """
        Generate a Majora's Mask Randomizer seed.
        
        Returns:
            URL to the generated seed
        """
        # TODO: Implement MMR seed generation
        return "https://example.com/mmr-seed-url"
    
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
    
    async def _generate_wwr(self) -> str:
        """
        Generate a Wind Waker Randomizer seed.
        
        Returns:
            URL to the generated seed
        """
        # TODO: Implement WWR seed generation
        return "https://example.com/wwr-seed-url"
    
    async def _generate_test(self) -> str:
        """
        Generate a test seed (for testing purposes).
        
        Returns:
            URL to a test seed
        """
        await asyncio.sleep(5)  # Simulate processing time
        return "https://example.com/test-seed-url"
