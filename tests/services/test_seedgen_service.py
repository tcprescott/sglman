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
            'alttpr', 'ff1r', 'z1r', 'smmap', 'ootr', 'test'
        }

    def test_mmr_and_wwr_not_registered(self):
        # No usable public seed API exists for MMR/WWR, so their generators
        # were removed; they must never appear as selectable randomizers.
        assert 'mmr' not in SeedGenerationService.AVAILABLE_RANDOMIZERS
        assert 'wwr' not in SeedGenerationService.AVAILABLE_RANDOMIZERS


# ---------------------------------------------------------------------------
# Removed generator stubs
# ---------------------------------------------------------------------------


class TestRemovedGenerators:
    def test_mmr_generator_method_is_gone(self, service):
        assert not hasattr(service, '_generate_mmr')

    def test_wwr_generator_method_is_gone(self, service):
        assert not hasattr(service, '_generate_wwr')


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

    @pytest.mark.parametrize('randomizer', ['mmr', 'wwr'])
    async def test_raises_for_removed_randomizer(self, service, randomizer):
        with pytest.raises(ValueError, match='Unsupported'):
            await service.generate_seed(randomizer)

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
        # No ALTTPR.generate / aiohttp / OOTR_API_KEY needed: the mock returns
        # before any backend is reached — even for randomizers that would
        # otherwise raise for missing credentials (smmap/ootr).
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('MOCK_SEEDGEN', 'true')
        monkeypatch.delenv('OOTR_API_KEY', raising=False)
        monkeypatch.delenv('SMMAP_SPOILER_TOKEN', raising=False)
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
        from application.utils.mock_seedgen import is_mock_seedgen

        monkeypatch.delenv('MOCK_SEEDGEN', raising=False)
        assert is_mock_seedgen() is False

    def test_helper_refuses_in_production(self, monkeypatch):
        from application.utils.mock_seedgen import is_mock_seedgen

        monkeypatch.setenv('MOCK_SEEDGEN', 'true')
        monkeypatch.setenv('ENVIRONMENT', 'production')
        with pytest.raises(RuntimeError, match='must not be enabled in production'):
            is_mock_seedgen()


# ---------------------------------------------------------------------------
# _generate_ff1r — pure URL manipulation, no network
# ---------------------------------------------------------------------------


class TestGenerateFf1r:
    async def test_returns_url_with_seed_param(self, service):
        result = await service._generate_ff1r()
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
            parse_qs(urlparse(await service._generate_ff1r()).query)['s'][0]
            for _ in range(5)
        }
        assert len(seeds) > 1


# ---------------------------------------------------------------------------
# _generate_z1r — pure local computation, no network
# ---------------------------------------------------------------------------


class TestGenerateZ1r:
    async def test_returns_string_with_flags(self, service):
        result = await service._generate_z1r()
        assert ' - ' in result
        # Left side is the seed integer, right side is the flags string
        parts = result.split(' - ', 1)
        assert len(parts) == 2
        seed_part = parts[0]
        assert seed_part.isdigit()
