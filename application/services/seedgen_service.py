"""
Seed Generation Service - Business Logic Layer

Handles random seed generation for various randomizers.
Supports: ALTTPR, FF1R, Z1R, SMMAP, OOTR, DK64R, and Test.
Registers not-yet-implemented stubs: MMR, SMDASH, WWR.
"""

import asyncio
import json
import os
import random
import secrets
import time
import urllib.parse
from typing import List, Optional, Set

import aiohttp
import yaml
from pyz3r import ALTTPR

from application.tenant_context import require_tenant_id
from application.utils.mock_seedgen import is_mock_seedgen
from models import FeatureFlag, Preset

# DK64 Randomizer (api.dk64rando.com) — a task-queue backend: submit → poll →
# result. See docs/online-tournaments/implementation/dk64-randomizer.md.
DK64R_API_BASE = 'https://api.dk64rando.com/api'
DK64R_BRANCHES = {'stable', 'dev'}
# The player-facing site host per branch (the permalink the roll returns).
DK64R_SITE_HOSTS = {'stable': 'dk64randomizer.com', 'dev': 'dev.dk64randomizer.com'}
DK64R_POLL_INTERVAL = 5.0        # seconds — matches the reference web client's cadence
DK64R_GENERATION_TIMEOUT = 600.0  # seconds (10 min) worst-case queue + generation budget


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
    # wired to an upstream API — rolling one raises ``ValueError``.
    STUB_RANDOMIZERS = {'mmr', 'smdash', 'wwr'}

    # Randomizers whose generator resolves a ``Preset`` (its settings feed the
    # roll). Anything else ignores the preset and rolls hard-coded settings.
    PRESET_AWARE_RANDOMIZERS = {'alttpr', 'dk64r'}

    # Randomizers gated behind a per-tenant feature flag: they reach an upstream
    # that requires an API key whose owner attaches usage restrictions the
    # community must be authorized (and have agreed) to use. Availability of the
    # flag is how a super-admin records that authorization. The mapping is used
    # to filter selector surfaces and to gate every roll boundary.
    FLAG_GATED_RANDOMIZERS = {'dk64r': FeatureFlag.DK64_RANDOMIZER}

    # Randomizers whose generator can embed community triforce texts.
    TRIFORCE_TEXT_RANDOMIZERS = {'alttpr'}

    @classmethod
    def supports_triforce_texts(cls, generator: Optional[str]) -> bool:
        return generator in cls.TRIFORCE_TEXT_RANDOMIZERS

    @classmethod
    def gating_flag(cls, randomizer: Optional[str]) -> Optional[FeatureFlag]:
        """The feature flag gating ``randomizer``, or ``None`` when it is ungated.

        Every roll boundary (match schedule, REST roll, qualifier pool roll)
        consults this to enforce the usage agreement at call time.
        """
        return cls.FLAG_GATED_RANDOMIZERS.get(randomizer)

    @classmethod
    def available_randomizers(cls, live_flags: Set[FeatureFlag]) -> List[str]:
        """The randomizers a tenant may *select*, given its live feature flags.

        Drops any flag-gated randomizer whose flag is not live. Validity is not
        availability: ``AVAILABLE_RANDOMIZERS`` stays the whole set (a stored
        ``dk64r`` preset is a valid row even where the flag is off), while the
        two selector surfaces offer only what the tenant is authorized to use.
        """
        return [
            r for r in cls.AVAILABLE_RANDOMIZERS
            if r not in cls.FLAG_GATED_RANDOMIZERS or cls.FLAG_GATED_RANDOMIZERS[r] in live_flags
        ]

    async def generate_seed(self, randomizer: str, preset: Optional[Preset] = None) -> str:
        """
        Generate a seed for the specified randomizer.

        Args:
            randomizer: Name of the randomizer (alttpr, ff1r, z1r, smmap, ootr, test)
            preset: Optional resolved ``Preset`` supplying the randomizer settings.
                Preset-aware backends (``PRESET_AWARE_RANDOMIZERS``: ALTTPR, DK64R)
                use ``preset.settings`` when given and fall back to a committed
                default without one. Other backends are still hard-coded and
                ignore the preset.

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

        if randomizer in self.PRESET_AWARE_RANDOMIZERS:
            return await generator_map[randomizer](preset)
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
        raise ValueError("Majora's Mask Randomizer seed generation is not yet implemented.")

    async def _generate_smdash(self) -> str:
        """Generate a Super Metroid: DASH seed. Not yet implemented."""
        raise ValueError("Super Metroid: DASH seed generation is not yet implemented.")

    async def _generate_dk64r(self, preset: Optional[Preset] = None) -> str:
        """Generate a Donkey Kong 64 Randomizer seed via the api.dk64rando.com queue.

        The upstream is a task queue: convert settings (if needed), submit the
        task, poll until it finishes, and return a shareable dk64randomizer.com
        permalink. The API is key-gated (``DK64R_API_KEY``, sent as ``X-API-Key``)
        — which is why the ``dk64r`` randomizer is flag-gated at every roll
        boundary. See docs/online-tournaments/implementation/dk64-randomizer.md.
        """
        api_key = os.environ.get('DK64R_API_KEY')
        if not api_key:
            raise ValueError('DK64R_API_KEY is not configured.')

        # Resolve settings: the preset when given, else the committed default.
        if preset is not None:
            settings = dict(preset.settings or {})
        else:
            # Read off the shared event loop — a blocking file read stalls every
            # connected user (CLAUDE.md: never block the event loop).
            def _read_default() -> dict:
                with open("presets/dk64r/sgl.json", "r", encoding="utf-8") as f:
                    return json.load(f)

            settings = await asyncio.to_thread(_read_default)

        # Optional per-preset branch override, stripped before anything is sent.
        branch = str(settings.pop('_branch', 'stable'))
        if branch not in DK64R_BRANCHES:
            raise ValueError(
                f"Unknown DK64R branch '{branch}' (expected 'stable' or 'dev')."
            )

        # A settings string is the site's own portable preset format; expand it
        # to the full settings dict. A full-JSON preset is submitted as-is
        # (converting a dict would yield a string — the opposite direction).
        settings_string = settings.get('settings_string')

        params = {'branch': branch}
        headers = {'X-API-Key': api_key}
        async with aiohttp.ClientSession(headers=headers) as session:
            if settings_string is not None:
                settings_dict = await self._dk64r_convert(session, settings_string, params)
            else:
                settings_dict = settings
            task_id = await self._dk64r_submit(session, settings_dict, params)
            result = await self._dk64r_poll(session, task_id, params)

        seed_number = result.get('seed_number')
        if seed_number is None:
            raise ValueError('DK64 Randomizer returned no seed identifier.')
        return f"https://{DK64R_SITE_HOSTS[branch]}/randomizer.html?seed_id={seed_number}"

    async def _dk64r_convert(self, session, settings_string: str, params: dict) -> dict:
        """Expand a DK64R settings string into the full settings JSON object."""
        async with session.post(
            f"{DK64R_API_BASE}/convert_settings",
            json={'settings': settings_string}, params=params,
        ) as resp:
            if resp.status != 200:
                raise ValueError(await self._dk64r_error(resp, 'convert settings'))
            data = await resp.json()
        if not isinstance(data, dict):
            raise ValueError('DK64 Randomizer returned an unexpected settings payload.')
        return data

    async def _dk64r_submit(self, session, settings_dict: dict, params: dict) -> str:
        """Submit a generation task; return its task id."""
        async with session.post(
            f"{DK64R_API_BASE}/submit-task",
            json={'settings_data': json.dumps(settings_dict)}, params=params,
        ) as resp:
            if resp.status != 200:
                raise ValueError(await self._dk64r_error(resp, 'submit the seed'))
            data = await resp.json()
        task_id = (data or {}).get('task_id')
        if not task_id:
            raise ValueError('DK64 Randomizer did not return a task id.')
        return task_id

    async def _dk64r_poll(self, session, task_id: str, params: dict) -> dict:
        """Poll a task until it finishes; return its ``result`` object.

        Bounded by ``DK64R_GENERATION_TIMEOUT``. A crashed task surfaces as HTTP
        500; the reference client also defends against a ``failed`` status inside
        a 200, so both are handled.
        """
        deadline = time.monotonic() + DK64R_GENERATION_TIMEOUT
        while True:
            async with session.get(
                f"{DK64R_API_BASE}/task-status/{task_id}", params=params,
            ) as resp:
                if resp.status != 200:
                    raise ValueError(await self._dk64r_error(resp, 'generate the seed'))
                data = await resp.json()
            status = (data or {}).get('status')
            if status == 'finished':
                result = data.get('result')
                if not isinstance(result, dict):
                    raise ValueError('DK64 Randomizer finished without a seed result.')
                return result
            if status == 'failed':
                raise ValueError('DK64 Randomizer failed to generate the seed.')
            if status not in ('queued', 'started'):
                raise ValueError(
                    f"DK64 Randomizer returned an unexpected status '{status}'."
                )
            if time.monotonic() >= deadline:
                raise ValueError('DK64 Randomizer seed generation timed out.')
            await asyncio.sleep(DK64R_POLL_INTERVAL)

    @staticmethod
    async def _dk64r_error(resp, action: str) -> str:
        """Best-effort upstream error text for a failed DK64R call."""
        detail = ''
        try:
            body = await resp.json()
            if isinstance(body, dict):
                detail = body.get('error') or body.get('message') or ''
        except Exception:
            try:
                detail = (await resp.text())[:200]
            except Exception:
                detail = ''
        suffix = f': {detail}' if detail else ''
        return f"DK64 Randomizer failed to {action} (HTTP {resp.status}){suffix}"

    async def _generate_wwr(self) -> str:
        """Generate a Wind Waker Randomizer seed. Not yet implemented."""
        raise ValueError("Wind Waker Randomizer seed generation is not yet implemented.")

    async def _generate_test(self) -> str:
        """
        Generate a test seed (for testing purposes).
        
        Returns:
            URL to a test seed
        """
        await asyncio.sleep(5)  # Simulate processing time
        return "https://example.com/test-seed-url"
