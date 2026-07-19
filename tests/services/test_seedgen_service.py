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
    @pytest.mark.parametrize('randomizer', ['alttpr', 'ff1r', 'z1r', 'smmap', 'ootr', 'dk64r', 'test'])
    async def test_returns_mock_url_without_network(self, service, monkeypatch, randomizer):
        # No ALTTPR.generate / aiohttp / OOTR_API_KEY / DK64R_API_KEY needed: the
        # mock returns before any backend is reached — even for randomizers that
        # would otherwise raise for missing credentials (smmap/ootr/dk64r).
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('MOCK_SEEDGEN', 'true')
        monkeypatch.delenv('OOTR_API_KEY', raising=False)
        monkeypatch.delenv('SMMAP_SPOILER_TOKEN', raising=False)
        monkeypatch.delenv('DK64R_API_KEY', raising=False)
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


# ---------------------------------------------------------------------------
# available_randomizers / gating_flag — the flag-gated selector filter
# ---------------------------------------------------------------------------


class TestRandomizerAvailability:
    def test_dk64r_gated_by_dk64_flag(self):
        from models import FeatureFlag
        assert SeedGenerationService.gating_flag('dk64r') is FeatureFlag.DK64_RANDOMIZER

    def test_ungated_randomizer_has_no_gating_flag(self):
        assert SeedGenerationService.gating_flag('alttpr') is None
        assert SeedGenerationService.gating_flag('ootr') is None

    def test_dk64r_present_only_when_flag_live(self):
        from models import FeatureFlag
        without = SeedGenerationService.available_randomizers(set())
        assert 'dk64r' not in without
        withflag = SeedGenerationService.available_randomizers({FeatureFlag.DK64_RANDOMIZER})
        assert 'dk64r' in withflag

    def test_ungated_randomizers_always_present(self):
        available = SeedGenerationService.available_randomizers(set())
        for r in ('alttpr', 'ff1r', 'z1r', 'smmap', 'ootr', 'mmr', 'smdash', 'wwr', 'test'):
            assert r in available
        # AVAILABLE_RANDOMIZERS stays whole — validity is not availability.
        assert 'dk64r' in SeedGenerationService.AVAILABLE_RANDOMIZERS


# ---------------------------------------------------------------------------
# _generate_dk64r — task-queue backend (all HTTP faked; no network)
# ---------------------------------------------------------------------------


class _FakeResp:
    """A minimal aiohttp response context manager returning scripted data."""

    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def text(self):
        import json as _json
        return _json.dumps(self._payload) if not isinstance(self._payload, Exception) else 'error'


class _DK64RStub:
    """A fake ``aiohttp.ClientSession`` scripting DK64R's HTTP round-trips.

    Construct with an ordered list of ``(status, payload)`` responses consumed
    per request; ``default`` (if given) is reused once the list is exhausted.
    Records ``(method, url, kwargs)`` for each call and the session headers.
    """

    def __init__(self, responses, *, default=None):
        self._responses = list(responses)
        self._default = default
        self.calls = []
        self.headers = None

    def __call__(self, *args, **kwargs):  # aiohttp.ClientSession(headers=...)
        self.headers = kwargs.get('headers')
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _next(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        if self._responses:
            status, payload = self._responses.pop(0)
        elif self._default is not None:
            status, payload = self._default
        else:
            raise AssertionError('DK64RStub ran out of scripted responses')
        return _FakeResp(status, payload)

    def post(self, url, **kwargs):
        return self._next('POST', url, kwargs)

    def get(self, url, **kwargs):
        return self._next('GET', url, kwargs)


class TestGenerateDk64r:
    async def test_missing_api_key_raises(self, service, monkeypatch):
        monkeypatch.delenv('DK64R_API_KEY', raising=False)
        preset = _preset({'settings_string': 's'})
        with pytest.raises(ValueError, match='DK64R_API_KEY is not configured'):
            await service._generate_dk64r(preset)

    async def test_settings_string_happy_path(self, service, monkeypatch):
        monkeypatch.setenv('DK64R_API_KEY', 'secret-key')
        stub = _DK64RStub([
            (200, {'level_randomization': 'level_order'}),        # convert_settings
            (200, {'task_id': 'task-123', 'status': 'queued'}),   # submit-task
            (200, {'status': 'queued', 'position': 2}),           # poll
            (200, {'status': 'started'}),                          # poll
            (200, {'status': 'finished', 'result': {'seed_number': 90210, 'hash': 'DK-DK-DK'}}),
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        preset = _preset({'settings_string': 'abc123'})
        url = await service._generate_dk64r(preset)

        assert url == 'https://dk64randomizer.com/randomizer.html?seed_id=90210'
        # The API key travels as X-API-Key on the session.
        assert stub.headers == {'X-API-Key': 'secret-key'}
        # Convert was called with the settings string, submit with the expanded dict.
        assert stub.calls[0][1].endswith('/convert_settings')
        assert stub.calls[0][2]['json'] == {'settings': 'abc123'}
        assert stub.calls[0][2]['params'] == {'branch': 'stable'}
        assert stub.calls[1][1].endswith('/submit-task')
        import json as _json
        assert _json.loads(stub.calls[1][2]['json']['settings_data']) == {'level_randomization': 'level_order'}
        # Poll hits task-status for the returned task id.
        assert '/task-status/task-123' in stub.calls[2][1]

    async def test_full_json_preset_skips_convert(self, service, monkeypatch):
        monkeypatch.setenv('DK64R_API_KEY', 'k')
        stub = _DK64RStub([
            (200, {'task_id': 't1', 'status': 'queued'}),
            (200, {'status': 'finished', 'result': {'seed_number': 5}}),
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        preset = _preset({'level_randomization': 'level_order', 'krool_phases': 5})
        url = await service._generate_dk64r(preset)

        assert url.endswith('seed_id=5')
        # First (and only POST) call is submit — no convert step.
        assert stub.calls[0][1].endswith('/submit-task')
        import json as _json
        assert _json.loads(stub.calls[0][2]['json']['settings_data']) == {
            'level_randomization': 'level_order', 'krool_phases': 5,
        }

    async def test_dev_branch_routes_to_dev_host_and_is_stripped(self, service, monkeypatch):
        monkeypatch.setenv('DK64R_API_KEY', 'k')
        stub = _DK64RStub([
            (200, {'task_id': 't1', 'status': 'queued'}),
            (200, {'status': 'finished', 'result': {'seed_number': 77}}),
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        preset = _preset({'_branch': 'dev', 'krool_phases': 3})
        url = await service._generate_dk64r(preset)

        assert url == 'https://dev.dk64randomizer.com/randomizer.html?seed_id=77'
        # Every call carries branch=dev...
        assert stub.calls[0][2]['params'] == {'branch': 'dev'}
        # ...and _branch never leaks into the submitted settings.
        import json as _json
        assert '_branch' not in _json.loads(stub.calls[0][2]['json']['settings_data'])

    async def test_unknown_branch_raises(self, service, monkeypatch):
        monkeypatch.setenv('DK64R_API_KEY', 'k')
        preset = _preset({'_branch': 'nightly', 'krool_phases': 3})
        with pytest.raises(ValueError, match='Unknown DK64R branch'):
            await service._generate_dk64r(preset)

    async def test_no_preset_falls_back_to_builtin_file(self, service, monkeypatch):
        monkeypatch.setenv('DK64R_API_KEY', 'k')
        stub = _DK64RStub([
            (200, {'expanded': True}),                             # convert (builtin is a settings string)
            (200, {'task_id': 't1', 'status': 'queued'}),
            (200, {'status': 'finished', 'result': {'seed_number': 1}}),
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        url = await service._generate_dk64r(None)
        assert url.endswith('seed_id=1')
        # The committed builtin is a settings-string preset → convert runs first.
        assert stub.calls[0][1].endswith('/convert_settings')

    async def test_submit_rejection_raises(self, service, monkeypatch):
        monkeypatch.setenv('DK64R_API_KEY', 'k')
        stub = _DK64RStub([
            (400, {'error': 'invalid settings_data'}),            # submit-task 400
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)

        preset = _preset({'krool_phases': 3})
        with pytest.raises(ValueError, match='invalid settings_data'):
            await service._generate_dk64r(preset)

    async def test_task_crash_http_500_raises(self, service, monkeypatch):
        monkeypatch.setenv('DK64R_API_KEY', 'k')
        stub = _DK64RStub([
            (200, {'task_id': 't1', 'status': 'queued'}),
            (500, {'error': 'generator exploded'}),               # task-status 500
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        preset = _preset({'krool_phases': 3})
        with pytest.raises(ValueError, match='generate the seed'):
            await service._generate_dk64r(preset)

    async def test_failed_status_raises(self, service, monkeypatch):
        monkeypatch.setenv('DK64R_API_KEY', 'k')
        stub = _DK64RStub([
            (200, {'task_id': 't1', 'status': 'queued'}),
            (200, {'status': 'failed'}),                          # defensive failed inside 200
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        preset = _preset({'krool_phases': 3})
        with pytest.raises(ValueError, match='failed to generate'):
            await service._generate_dk64r(preset)

    async def test_poll_timeout_raises(self, service, monkeypatch):
        monkeypatch.setenv('DK64R_API_KEY', 'k')
        stub = _DK64RStub(
            [(200, {'task_id': 't1', 'status': 'queued'})],
            default=(200, {'status': 'queued', 'position': 9}),   # never finishes
        )
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)
        # Advance the monotonic clock past the deadline. A never-exhausting
        # counter (vs. a fixed iterator) is safe even if teardown reads the clock.
        import itertools
        clock = itertools.count(0.0, 10_000.0)
        monkeypatch.setattr(
            'application.services.seedgen_service.time.monotonic',
            lambda: next(clock),
        )

        preset = _preset({'krool_phases': 3})
        with pytest.raises(ValueError, match='timed out'):
            await service._generate_dk64r(preset)


async def _noop_sleep(_seconds):
    return None


def _preset(settings):
    from types import SimpleNamespace
    return SimpleNamespace(randomizer='dk64r', settings=settings)
