"""
Seed Generation Service - Business Logic Layer

Handles random seed generation for various randomizers.
Supports: ALTTPR, FF1R, Z1R, SMMAP, OOTR, DK64R, and Test.
Registers not-yet-implemented stubs: MMR, SMDASH, WWR.
"""

import asyncio
import json
import random
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, List, Optional, Set

import aiohttp
import yaml
from pyz3r import ALTTPR

from application.errors import MissingCredentialError
from application.randomizer_credentials import credentials_for, spec_for
from application.tenant_context import require_tenant_id
from application.utils.mocks.mock_seedgen import is_mock_seedgen
from application.utils.seed_provider import (
    PROVIDER_MAX_ATTEMPTS,
    PROVIDER_TIMEOUT_SECONDS,
    ProviderCall,
    SeedProviderBadResponse,
    call_provider,
    raise_for_status,
)
from models import Preset

# DK64 Randomizer (api.dk64rando.com) — a task-queue backend: submit → poll →
# result.
DK64R_API_BASE = 'https://api.dk64rando.com/api'
DK64R_BRANCHES = {'stable', 'dev'}
# The player-facing site host per branch (the permalink the roll returns).
DK64R_SITE_HOSTS = {'stable': 'dk64randomizer.com', 'dev': 'dev.dk64randomizer.com'}
DK64R_POLL_INTERVAL = 5.0        # seconds — matches the reference web client's cadence
DK64R_GENERATION_TIMEOUT = 600.0  # seconds (10 min) worst-case queue + generation budget


@dataclass
class RolledSeed:
    """What a generator produced: the permalink, and the settings that made it.

    ``settings`` is the **resolved payload as sent upstream**, which is the whole
    reason it is carried back here rather than re-derived by the caller. A
    ``Preset`` is an editable row: without a snapshot taken at roll time, editing
    a preset silently rewrites the apparent history of every seed rolled from it,
    and the question a disputed result actually asks — "what settings did this
    seed use?" — has no answer. ``None`` where the generator has no settings to
    speak of (the test stub).
    """

    url: str
    settings: Optional[dict] = None


async def _read_bundled_preset(path: str) -> str:
    """Read a committed preset file without blocking the shared event loop.

    These are small files that ship in the image, but every connected client
    shares one loop — a synchronous ``open()`` on a seed roll stalls all of
    them, so the read hops to a worker thread.
    """
    return await asyncio.to_thread(Path(path).read_text, encoding='utf-8')


class SeedGenerationService:
    """Service for generating seeds for various randomizers."""

    # Available randomizers
    AVAILABLE_RANDOMIZERS: ClassVar[List[str]] = [
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
    STUB_RANDOMIZERS: ClassVar[Set[str]] = {'mmr', 'smdash', 'wwr'}

    # Randomizers whose generator resolves a ``Preset`` (its settings feed the
    # roll). Anything else ignores the preset and rolls hard-coded settings.
    PRESET_AWARE_RANDOMIZERS: ClassVar[Set[str]] = {'alttpr', 'dk64r'}

    # Randomizers whose generator can embed community triforce texts.
    TRIFORCE_TEXT_RANDOMIZERS: ClassVar[Set[str]] = {'alttpr'}

    # Per-provider overrides of the shared execution contract
    # (``application.utils.seed_provider``). Anything absent takes the defaults.
    #
    # DK64R is the one that must differ on both axes: its upstream is a task
    # queue whose *whole* roll (submit → poll → result) legitimately runs for
    # minutes, so the outer budget has to exceed the poll deadline rather than
    # cut it short — and re-running that roll would submit a second generation
    # task, so it gets exactly one attempt. Retrying the individual requests
    # inside it is safe and is handled within the generator.
    PROVIDER_TIMEOUTS: ClassVar[dict] = {
        'dk64r': DK64R_GENERATION_TIMEOUT + 60.0,
    }
    PROVIDER_ATTEMPTS: ClassVar[dict] = {
        'dk64r': 1,
    }

    @classmethod
    def supports_triforce_texts(cls, generator: Optional[str]) -> bool:
        return generator in cls.TRIFORCE_TEXT_RANDOMIZERS

    @classmethod
    def available_randomizers(cls, configured: Set[str]) -> List[str]:
        """The randomizers a tenant may *select*, given the credentials it has set.

        ``configured`` is ``RandomizerCredentialService.configured_randomizers()``.
        Drops any randomizer whose upstream needs a key the community has not
        supplied — validity is not availability: ``AVAILABLE_RANDOMIZERS`` stays
        the whole set (a stored ``dk64r`` preset is a valid row with or without a
        key, and each editor re-adds its own row's randomizer), while the selector
        surfaces offer only what this community can actually roll.
        """
        return [
            r for r in cls.AVAILABLE_RANDOMIZERS
            if not credentials_for(r) or r in configured
        ]

    async def _credential(self, randomizer: str, key: str) -> str:
        """This tenant's value for one randomizer credential.

        The successor to the process-wide ``*_API_KEY`` env vars: credentials are
        per tenant with no deployment-wide fallback, so a community that has not
        supplied one gets a clear error instead of silently rolling on someone
        else's key. Called from inside a generator, i.e. after the ``MOCK_SEEDGEN``
        short-circuit, so mock rolls still need no credentials.
        """
        from application.services.randomizer_credential_service import (
            RandomizerCredentialService,
        )

        value = await RandomizerCredentialService().resolve(randomizer, key)
        if not value:
            raise MissingCredentialError(
                f'{spec_for(randomizer, key).label} is not configured for this '
                f'community. Add it under Admin → Randomizer Keys.'
            )
        return value

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
            ValueError: If randomizer is not supported, or a
                :class:`~application.utils.seed_provider.SeedProviderError`
                subclass naming what the upstream did.
        """
        call = await self.generate_seed_call(randomizer, preset)
        return call.value.url

    async def generate_seed_call(
        self,
        randomizer: str,
        preset: Optional[Preset] = None,
        *,
        surface: Optional[str] = None,
    ) -> ProviderCall:
        """Roll a seed under the provider contract, returning it with its cost.

        The provenance-carrying entry point: the returned
        :class:`~application.utils.seed_provider.ProviderCall` holds the
        :class:`RolledSeed` (permalink + settings as sent) plus the attempt count
        and latency, which is what a ``GeneratedSeeds`` row records. Prefer this
        over :meth:`generate_seed` anywhere the roll is persisted.
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
            return ProviderCall(
                value=RolledSeed(url=self._mock_seed_url(randomizer)),
                provider=randomizer, operation='generate_seed', surface=surface,
            )

        generator = generator_map[randomizer]
        if randomizer in self.PRESET_AWARE_RANDOMIZERS:
            def _run():
                return generator(preset)
        else:
            def _run():
                return generator()

        return await call_provider(
            _run,
            provider=randomizer,
            operation='generate_seed',
            surface=surface,
            timeout=self.PROVIDER_TIMEOUTS.get(randomizer, PROVIDER_TIMEOUT_SECONDS),
            max_attempts=self.PROVIDER_ATTEMPTS.get(randomizer, PROVIDER_MAX_ATTEMPTS),
        )

    @staticmethod
    def _mock_seed_url(randomizer: str) -> str:
        """A believable, unique permalink for MOCK_SEEDGEN mode."""
        return f"https://mock.seedgen.local/{randomizer}/{secrets.token_hex(8)}"

    async def _generate_alttpr(self, preset: Optional[Preset] = None) -> RolledSeed:
        """
        Generate an A Link to the Past Randomizer seed.

        Uses ``preset.settings`` when a preset is supplied; otherwise falls back
        to the built-in ``casualboots`` settings (the historical default).
        """
        if preset is not None:
            settings = preset.settings
        else:
            settings = yaml.safe_load(
                await _read_bundled_preset("presets/alttpr/casualboots.yaml")
            )['settings']

        seed = await ALTTPR.generate(
            settings=settings,
            endpoint='/api/customizer',
        )
        return RolledSeed(url=seed.url, settings=settings)

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

        preset = yaml.safe_load(
            await _read_bundled_preset("presets/alttpr/casualboots.yaml")
        )

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
    
    async def _generate_ff1r(self) -> RolledSeed:
        """
        Generate a Final Fantasy 1 Randomizer seed.

        Purely local: the flag string is fixed and only the seed number varies,
        so there is no upstream to fail.
        """
        url = 'https://4-8-6.finalfantasyrandomizer.com/?s=00000000&f=6XOcCG.geJ.YDwt9.jijRao2NoTvBlq0V2VvHuAxjtMhlVRYso0wmNtUopSO9Xzt2k8Gn7v9d6ysABeksoaTevatcw4ZKZoMV95h1NQISZlbvlK8FEwtAAT5KWQUztLnkzQuDcO36uLraMFFQpGq0YsZrZHr7YdUoUxsW5.IutAsHfjB'
        seed = ('%008x' % random.randrange(16 ** 8)).upper()
        up = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(up.query)
        qs['s'] = seed
        newurl = urllib.parse.urlunparse((up.scheme, up.netloc, up.path, up.params,
                                          urllib.parse.urlencode(qs, doseq=True), up.fragment))
        return RolledSeed(url=newurl, settings={'seed': seed, 'flags': qs.get('f', [''])[0]})

    async def _generate_z1r(self) -> RolledSeed:
        """
        Generate a Zelda 1 Randomizer seed.

        Returns a "seed - flags" string rather than a URL; purely local.
        """
        flags = '5K!ELDXj35eUlQNR4XAhcL18nJBPgbC4Hpw'
        seed = random.randint(0, 8999999999999999999)
        return RolledSeed(
            url=f"{seed} - {flags}", settings={'seed': str(seed), 'flags': flags},
        )

    async def _generate_smmap(self) -> RolledSeed:
        """
        Generate a Super Metroid Map Randomizer seed.
        """
        # Never fall back to a committed default — a leaked spoiler token
        # unlocks spoiler logs for race seeds.
        spoiler_token = await self._credential('smmap', 'spoiler_token')
        settings = await _read_bundled_preset("presets/smmap/community_race_s4.json")

        async with aiohttp.ClientSession() as session:
            with aiohttp.MultipartWriter('form-data') as mpwriter:
                mpwriter.append(spoiler_token).set_content_disposition('form-data', name='spoiler_token')
                mpwriter.append(settings).set_content_disposition('form-data', name='settings')
            async with session.post('https://maprando.com/randomize', data=mpwriter) as resp:
                # Read the status before the body: an error page is HTML, and
                # parsing it as JSON would report a parse failure instead of the
                # 503 that caused it.
                await raise_for_status(resp, provider='smmap', operation='generate_seed')
                data = await resp.json()

        seed_url = (data or {}).get('seed_url')
        if not seed_url:
            raise SeedProviderBadResponse(
                'Map Rando returned no seed URL.',
                provider='smmap', operation='generate_seed',
            )
        # The spoiler token is a credential and is deliberately not part of the
        # snapshot — settings only.
        return RolledSeed(
            url=f"https://maprando.com{seed_url}", settings=json.loads(settings),
        )

    async def _generate_ootr(self) -> RolledSeed:
        """
        Generate an Ocarina of Time Randomizer seed.
        """
        settings = json.loads(await _read_bundled_preset("presets/ootr/sgl25.json"))

        # The OOTR API authenticates via a ``key`` query parameter; guard
        # against silently sending key=None when it is not configured.
        api_key = await self._credential('ootr', 'api_key')

        async with aiohttp.request(
            method='post',
            url="https://ootrandomizer.com/api/sglive/seed/create",
            json=settings,
            params={
                "key": api_key,
                "version": "8.3.0",
                "encrypt": "true"
            }
        ) as resp:
            await raise_for_status(resp, provider='ootr', operation='generate_seed')
            result = await resp.json()

        seed_id = (result or {}).get('id')
        if not seed_id:
            raise SeedProviderBadResponse(
                'OoT Randomizer returned no seed id.',
                provider='ootr', operation='generate_seed',
            )
        return RolledSeed(
            url=f"https://ootrandomizer.com/seed/get?id={seed_id}", settings=settings,
        )
    
    async def _generate_mmr(self) -> str:
        """Generate a Majora's Mask Randomizer seed. Not yet implemented."""
        raise ValueError("Majora's Mask Randomizer seed generation is not yet implemented.")

    async def _generate_smdash(self) -> str:
        """Generate a Super Metroid: DASH seed. Not yet implemented."""
        raise ValueError("Super Metroid: DASH seed generation is not yet implemented.")

    async def _generate_dk64r(self, preset: Optional[Preset] = None) -> RolledSeed:
        """Generate a Donkey Kong 64 Randomizer seed via the api.dk64rando.com queue.

        The upstream is a task queue: convert settings (if needed), submit the
        task, poll until it finishes, and return a shareable dk64randomizer.com
        permalink. The API is key-gated: the community's own key is sent as the
        ``X-API-Key`` header on every call.
        """
        api_key = await self._credential('dk64r', 'api_key')

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
        return RolledSeed(
            url=f"https://{DK64R_SITE_HOSTS[branch]}/randomizer.html?seed_id={seed_number}",
            settings={'branch': branch, **settings_dict},
        )

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

    async def _generate_test(self) -> RolledSeed:
        """
        Generate a test seed (for testing purposes).

        The deliberate sleep exercises the UI's in-progress state; it is not a
        provider call and has no settings to snapshot.
        """
        await asyncio.sleep(5)  # Simulate processing time
        return RolledSeed(url="https://example.com/test-seed-url")
