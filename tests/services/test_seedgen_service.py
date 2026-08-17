"""Tests for SeedGenerationService (unit — no network calls)."""

import pytest

from application.services.seedgen_service import SeedGenerationService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    return SeedGenerationService()


# ---------------------------------------------------------------------------
# supports_triforce_texts (classmethod)
# ---------------------------------------------------------------------------


class TestSupportsTriforceTexts:
    def test_alttpr_is_supported(self):
        assert SeedGenerationService.supports_triforce_texts('alttpr') is True

    def test_ff1r_is_not_supported(self):
        assert SeedGenerationService.supports_triforce_texts('ff1r') is False

    def test_none_is_not_supported(self):
        assert SeedGenerationService.supports_triforce_texts(None) is False

    def test_unknown_is_not_supported(self):
        assert SeedGenerationService.supports_triforce_texts('unknown') is False


# ---------------------------------------------------------------------------
# AVAILABLE_RANDOMIZERS list
# ---------------------------------------------------------------------------


class TestAvailableRandomizers:
    def test_alttpr_in_list(self):
        assert 'alttpr' in SeedGenerationService.AVAILABLE_RANDOMIZERS

    def test_test_in_list(self):
        assert 'test' in SeedGenerationService.AVAILABLE_RANDOMIZERS

    def test_all_entries_are_strings(self):
        assert all(isinstance(r, str) for r in SeedGenerationService.AVAILABLE_RANDOMIZERS)

    def test_exact_membership(self):
        assert set(SeedGenerationService.AVAILABLE_RANDOMIZERS) == {
            'alttpr', 'ff1r', 'z1r', 'smmap', 'ootr',
            'mmr', 'smdash', 'dk64r', 'wwr', 'test',
        }

    def test_stub_randomizers_are_registered(self):
        # Registered for selection but not yet wired to an upstream API.
        for stub in ('mmr', 'smdash', 'wwr'):
            assert stub in SeedGenerationService.AVAILABLE_RANDOMIZERS
            assert stub in SeedGenerationService.STUB_RANDOMIZERS

    def test_dk64r_is_no_longer_a_stub(self):
        # Promoted to a real backend (api.dk64rando.com); still selectable.
        assert 'dk64r' in SeedGenerationService.AVAILABLE_RANDOMIZERS
        assert 'dk64r' not in SeedGenerationService.STUB_RANDOMIZERS


# ---------------------------------------------------------------------------
# Stub generators — registered but not yet implemented
# ---------------------------------------------------------------------------


class TestStubGenerators:
    @pytest.mark.parametrize('randomizer', ['mmr', 'smdash', 'wwr'])
    def test_generator_method_exists(self, service, randomizer):
        assert hasattr(service, f'_generate_{randomizer}')

    @pytest.mark.parametrize('randomizer', ['mmr', 'smdash', 'wwr'])
    async def test_raises_not_implemented(self, service, randomizer):
        # Stub generators raise ValueError (the documented user-error contract),
        # so a user-reachable roll surfaces a 400 / UI warning rather than an
        # unhandled NotImplementedError -> 500 (audit §1.3).
        with pytest.raises(ValueError, match='not yet implemented'):
            await service.generate_seed(randomizer)


# ---------------------------------------------------------------------------
# generate_seed — unsupported randomizer
# ---------------------------------------------------------------------------


class TestGenerateSeed:
    async def test_raises_for_unsupported_randomizer(self, service):
        with pytest.raises(ValueError, match='Unsupported'):
            await service.generate_seed('unsupported_randomizer')

    async def test_raises_for_empty_string(self, service):
        with pytest.raises(ValueError, match='Unsupported'):
            await service.generate_seed('')

    async def test_test_generator_returns_url(self, service):
        """The 'test' generator has a 5-second sleep which we patch out."""
        from unittest.mock import patch

        async def fast_sleep(_):
            pass

        with patch('asyncio.sleep', fast_sleep):
            result = await service.generate_seed('test')
        assert result.startswith('https://')


# ---------------------------------------------------------------------------
# generate_seed — ALTTPR preset selection (no network; ALTTPR.generate patched)
# ---------------------------------------------------------------------------


class TestGenerateSeedPreset:
    async def test_alttpr_uses_preset_settings(self, service):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        preset = SimpleNamespace(randomizer='alttpr', settings={'mode': 'open', 'goal': 'ganon'})
        gen = AsyncMock(return_value=SimpleNamespace(url='https://alttpr.com/h/seed'))
        with patch('application.services.seedgen_service.ALTTPR.generate', gen):
            url = await service.generate_seed('alttpr', preset)

        assert url == 'https://alttpr.com/h/seed'
        # The preset's settings are handed to the randomizer verbatim.
        assert gen.await_args.kwargs['settings'] == {'mode': 'open', 'goal': 'ganon'}

    async def test_alttpr_without_preset_falls_back_to_builtin(self, service):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        gen = AsyncMock(return_value=SimpleNamespace(url='https://alttpr.com/h/builtin'))
        with patch('application.services.seedgen_service.ALTTPR.generate', gen):
            url = await service.generate_seed('alttpr')

        assert url == 'https://alttpr.com/h/builtin'
        # Falls back to the committed casualboots settings (a non-empty dict).
        settings = gen.await_args.kwargs['settings']
        assert isinstance(settings, dict) and settings


# ---------------------------------------------------------------------------
# generate_seed — MOCK_SEEDGEN short-circuit (no network for any randomizer)
# ---------------------------------------------------------------------------


class TestMockSeedgen:
    @pytest.mark.parametrize('randomizer', ['alttpr', 'ff1r', 'z1r', 'smmap', 'ootr', 'test'])
    async def test_returns_mock_url_without_network(self, service, monkeypatch, randomizer):
        # No ALTTPR.generate / aiohttp / credential rows needed: the mock returns
        # before any backend is reached — even for randomizers that would
        # otherwise raise for a missing credential (smmap/ootr). No ``db``
        # fixture either, which is the point: nothing touches the credential table.
        # ``dk64r`` is deliberately absent: it opts out of this short-circuit and
        # runs its own simulated queue (``TestMockDK64``).
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('MOCK_SEEDGEN', 'true')
        url = await service.generate_seed(randomizer)
        assert url.startswith(f'https://mock.seedgen.local/{randomizer}/')

    async def test_mock_urls_are_distinct(self, service, monkeypatch):
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('MOCK_SEEDGEN', 'true')
        urls = {await service.generate_seed('alttpr') for _ in range(10)}
        assert len(urls) == 10

    async def test_mock_still_rejects_unsupported_randomizer(self, service, monkeypatch):
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('MOCK_SEEDGEN', 'true')
        with pytest.raises(ValueError, match='Unsupported'):
            await service.generate_seed('not_a_randomizer')

    async def test_off_by_default_uses_real_generator(self, service, monkeypatch):
        # With MOCK_SEEDGEN unset, alttpr reaches ALTTPR.generate (patched here).
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        monkeypatch.delenv('MOCK_SEEDGEN', raising=False)
        gen = AsyncMock(return_value=SimpleNamespace(url='https://alttpr.com/h/real'))
        with patch('application.services.seedgen_service.ALTTPR.generate', gen):
            url = await service.generate_seed('alttpr')
        assert url == 'https://alttpr.com/h/real'

    def test_helper_off_by_default(self, monkeypatch):
        from application.utils.mocks.mock_seedgen import is_mock_seedgen

        monkeypatch.delenv('MOCK_SEEDGEN', raising=False)
        assert is_mock_seedgen() is False

    def test_helper_refuses_in_production(self, monkeypatch):
        from application.utils.mocks.mock_seedgen import is_mock_seedgen

        monkeypatch.setenv('MOCK_SEEDGEN', 'true')
        monkeypatch.setenv('ENVIRONMENT', 'production')
        with pytest.raises(RuntimeError, match='must not be enabled in production'):
            is_mock_seedgen()


# ---------------------------------------------------------------------------
# _generate_ff1r — pure URL manipulation, no network
# ---------------------------------------------------------------------------


class TestGenerateFf1r:
    async def test_returns_url_with_seed_param(self, service):
        result = (await service._generate_ff1r()).url
        assert '?s=' in result or '&s=' in result
        # Seed is 8 hex chars upper-cased
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(result).query)
        seed = qs.get('s', [None])[0]
        assert seed is not None
        assert len(seed) == 8

    async def test_is_randomized(self, service):
        from urllib.parse import parse_qs, urlparse

        seeds = {
            parse_qs(urlparse((await service._generate_ff1r()).url).query)['s'][0]
            for _ in range(5)
        }
        assert len(seeds) > 1


# ---------------------------------------------------------------------------
# _generate_z1r — pure local computation, no network
# ---------------------------------------------------------------------------


class TestGenerateZ1r:
    async def test_returns_string_with_flags(self, service):
        result = (await service._generate_z1r()).url
        assert ' - ' in result
        # Left side is the seed integer, right side is the flags string
        parts = result.split(' - ', 1)
        assert len(parts) == 2
        seed_part = parts[0]
        assert seed_part.isdigit()


# ---------------------------------------------------------------------------
# available_randomizers — the credential-driven selector filter
# ---------------------------------------------------------------------------


class TestRandomizerAvailability:
    def test_keyed_randomizers_hidden_without_credentials(self):
        available = SeedGenerationService.available_randomizers(set())
        for r in ('ootr', 'smmap', 'dk64r'):
            assert r not in available

    def test_keyed_randomizer_appears_once_configured(self):
        available = SeedGenerationService.available_randomizers({'dk64r'})
        assert 'dk64r' in available
        # Configuring one key says nothing about the others.
        assert 'ootr' not in available

    def test_credential_free_randomizers_always_present(self):
        available = SeedGenerationService.available_randomizers(set())
        for r in ('alttpr', 'ff1r', 'z1r', 'mmr', 'smdash', 'wwr', 'test'):
            assert r in available
        # AVAILABLE_RANDOMIZERS stays whole — validity is not availability.
        for r in ('ootr', 'smmap', 'dk64r'):
            assert r in SeedGenerationService.AVAILABLE_RANDOMIZERS


# ---------------------------------------------------------------------------
# Per-tenant credential resolution (the successor to the *_API_KEY env vars)
# ---------------------------------------------------------------------------


class TestCredentialResolution:
    @pytest.mark.parametrize('randomizer,key,label', [
        ('ootr', 'api_key', 'OoT Randomizer API key'),
        ('smmap', 'spoiler_token', 'Map Rando spoiler token'),
        ('dk64r', 'api_key', 'DK64 Randomizer API key'),
    ])
    async def test_missing_credential_names_it(self, service, db, randomizer, key, label):
        with pytest.raises(ValueError, match=f'{label} is not configured'):
            await service._credential(randomizer, key)

    async def test_configured_credential_is_returned_verbatim(self, service, db):
        from models import RandomizerCredential

        await RandomizerCredential.create(randomizer='ootr', key='api_key', value='abc123')
        assert await service._credential('ootr', 'api_key') == 'abc123'

    async def test_unknown_credential_is_rejected(self, service, db):
        with pytest.raises(ValueError, match='Unknown randomizer credential'):
            await service._credential('alttpr', 'api_key')
