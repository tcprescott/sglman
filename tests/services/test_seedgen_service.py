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


@pytest.fixture
async def dk64r_key(db):
    """The tenant's own DK64R credential — the successor to ``DK64R_API_KEY``.

    ``db`` binds the default test tenant, so the row is auto-stamped with it.
    """
    from models import RandomizerCredential

    await RandomizerCredential.create(randomizer='dk64r', key='api_key', value='k')


class TestGenerateDk64r:
    async def test_missing_credential_raises(self, service, db):
        preset = _preset({'settings_string': 's'})
        with pytest.raises(ValueError, match='DK64 Randomizer API key is not configured'):
            await service._generate_dk64r(preset)

    async def test_settings_string_happy_path(self, service, monkeypatch, dk64r_key):
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
        url = (await service._generate_dk64r(preset)).url

        assert url == 'https://dk64randomizer.com/randomizer.html?seed_id=90210'
        # The API key travels as X-API-Key on the session.
        assert stub.headers == {'X-API-Key': 'k'}
        # Convert was called with the settings string, submit with the expanded dict.
        assert stub.calls[0][1].endswith('/convert_settings')
        assert stub.calls[0][2]['json'] == {'settings': 'abc123'}
        assert stub.calls[0][2]['params'] == {'branch': 'stable'}
        assert stub.calls[1][1].endswith('/submit-task')
        import json as _json
        assert _json.loads(stub.calls[1][2]['json']['settings_data']) == {
            'level_randomization': 'level_order', 'generate_spoilerlog': False,
        }
        # Poll hits task-status for the returned task id.
        assert '/task-status/task-123' in stub.calls[2][1]

    async def test_full_json_preset_skips_convert(self, service, monkeypatch, dk64r_key):
        stub = _DK64RStub([
            (200, {'task_id': 't1', 'status': 'queued'}),
            (200, {'status': 'finished', 'result': {'seed_number': 5}}),
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        preset = _preset({'level_randomization': 'level_order', 'krool_phases': 5})
        url = (await service._generate_dk64r(preset)).url

        assert url.endswith('seed_id=5')
        # First (and only POST) call is submit — no convert step.
        assert stub.calls[0][1].endswith('/submit-task')
        import json as _json
        assert _json.loads(stub.calls[0][2]['json']['settings_data']) == {
            'level_randomization': 'level_order', 'krool_phases': 5,
            'generate_spoilerlog': False,
        }

    async def test_dev_branch_routes_to_dev_host_and_is_stripped(self, service, monkeypatch, dk64r_key):
        stub = _DK64RStub([
            (200, {'task_id': 't1', 'status': 'queued'}),
            (200, {'status': 'finished', 'result': {'seed_number': 77}}),
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        preset = _preset({'_branch': 'dev', 'krool_phases': 3})
        url = (await service._generate_dk64r(preset)).url

        assert url == 'https://dev.dk64randomizer.com/randomizer.html?seed_id=77'
        # Every call carries branch=dev...
        assert stub.calls[0][2]['params'] == {'branch': 'dev'}
        # ...and _branch never leaks into the submitted settings.
        import json as _json
        assert '_branch' not in _json.loads(stub.calls[0][2]['json']['settings_data'])

    async def test_unknown_branch_raises(self, service, monkeypatch, dk64r_key):
        preset = _preset({'_branch': 'nightly', 'krool_phases': 3})
        with pytest.raises(ValueError, match='Unknown DK64R branch'):
            await service._generate_dk64r(preset)

    async def test_no_preset_falls_back_to_builtin_file(self, service, monkeypatch, dk64r_key):
        stub = _DK64RStub([
            (200, {'expanded': True}),                             # convert (builtin is a settings string)
            (200, {'task_id': 't1', 'status': 'queued'}),
            (200, {'status': 'finished', 'result': {'seed_number': 1}}),
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        url = (await service._generate_dk64r(None)).url
        assert url.endswith('seed_id=1')
        # The committed builtin is a settings-string preset → convert runs first.
        assert stub.calls[0][1].endswith('/convert_settings')

    async def test_submit_rejection_raises(self, service, monkeypatch, dk64r_key):
        stub = _DK64RStub([
            (400, {'error': 'invalid settings_data'}),            # submit-task 400
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)

        preset = _preset({'krool_phases': 3})
        with pytest.raises(ValueError, match='invalid settings_data'):
            await service._generate_dk64r(preset)

    async def test_task_crash_http_500_raises(self, service, monkeypatch, dk64r_key):
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

    async def test_failed_status_raises(self, service, monkeypatch, dk64r_key):
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

    async def test_poll_timeout_raises(self, service, monkeypatch, dk64r_key):
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
            'application.services.seedgen_dk64r.time.monotonic',
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


class TestRemotePresetCatalogue:
    """``list_remote_presets`` — the randomizer's own published presets."""

    async def test_maps_entries_into_storable_presets(self, service, monkeypatch, dk64r_key):
        stub = _DK64RStub([(200, [
            {'branch': 'stable', 'name': 'Season 5', 'description': 'Race settings',
             'settings_string': 'abc123'},
        ])])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)

        presets = await service.list_remote_presets('dk64r', branch='stable')

        assert stub.calls[0][1].endswith('/get_presets')
        assert stub.calls[0][2]['params'] == {'branch': 'stable'}
        assert [(p.name, p.description) for p in presets] == [('Season 5', 'Race settings')]
        # Stored as the roll path reads it: the branch it came from, and the
        # portable string expanded through /convert_settings at roll time.
        assert presets[0].settings == {'_branch': 'stable', 'settings_string': 'abc123'}

    async def test_skips_unusable_entries(self, service, monkeypatch, dk64r_key):
        stub = _DK64RStub([(200, [
            {'name': 'No string'},
            {'settings_string': 'x'},
            'not an object',
            {'name': 'Keeper', 'settings_string': 'y'},
        ])])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)

        presets = await service.list_remote_presets('dk64r')
        # One malformed row must not cost the community the whole catalogue.
        assert [p.name for p in presets] == ['Keeper']

    async def test_non_list_payload_raises(self, service, monkeypatch, dk64r_key):
        stub = _DK64RStub([(200, {'presets': []})])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)

        with pytest.raises(ValueError, match='unexpected preset catalogue'):
            await service.list_remote_presets('dk64r')

    async def test_upstream_error_surfaces(self, service, monkeypatch, dk64r_key):
        stub = _DK64RStub([(500, {'error': 'boom'})] * 3)
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        with pytest.raises(ValueError, match='list the presets'):
            await service.list_remote_presets('dk64r')

    async def test_missing_credential_raises(self, service, db):
        with pytest.raises(ValueError, match='DK64 Randomizer API key is not configured'):
            await service.list_remote_presets('dk64r')

    async def test_randomizer_without_a_catalogue_raises(self, service):
        with pytest.raises(ValueError, match='does not publish a preset catalogue'):
            await service.list_remote_presets('ootr')

    def test_branch_helpers(self):
        assert SeedGenerationService.offers_remote_presets('dk64r')
        assert not SeedGenerationService.offers_remote_presets('alttpr')
        assert SeedGenerationService.remote_preset_branches('dk64r') == ['stable', 'dev']
        assert SeedGenerationService.remote_preset_branches('alttpr') == []


class TestMockDK64:
    """The simulated task queue (``MOCK_SEEDGEN`` + ``application.utils.mocks.mock_dk64``).

    Note the absence of the ``db`` and ``dk64r_key`` fixtures throughout: the
    simulated queue authenticates nobody, so a dev sandbox with no credential
    row rolls DK64 exactly like every other mocked backend.
    """

    @pytest.fixture(autouse=True)
    def _mock_env(self, monkeypatch):
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('MOCK_SEEDGEN', 'true')
        monkeypatch.setenv('MOCK_DK64_SECONDS', '0')

    async def test_returns_a_real_shaped_permalink(self, service):
        url = (await service._generate_dk64r(None)).url
        assert url.startswith('https://dk64randomizer.com/randomizer.html?seed_id=')

    async def test_does_not_return_the_generic_mock_url(self, service):
        # The whole point of opting out of the short-circuit: DK64 must travel
        # its own convert -> submit -> poll path even when mocked.
        url = await service.generate_seed('dk64r')
        assert 'mock.seedgen.local' not in url

    async def test_dev_branch_routes_to_dev_host(self, service):
        preset = _preset({'_branch': 'dev', 'settings_string': 'abc'})
        url = (await service._generate_dk64r(preset)).url
        assert url.startswith('https://dev.dk64randomizer.com/randomizer.html?seed_id=')

    async def test_seed_numbers_differ_between_rolls(self, service):
        urls = {(await service._generate_dk64r(None)).url for _ in range(5)}
        assert len(urls) > 1

    @pytest.mark.parametrize('outcome,message', [
        ('failed', 'failed to generate'),
        ('http_error', 'generate the seed'),
    ])
    async def test_failure_outcomes_raise(self, service, monkeypatch, outcome, message):
        monkeypatch.setenv('MOCK_DK64_OUTCOME', outcome)
        with pytest.raises(ValueError, match=message):
            await service._generate_dk64r(None)

    @pytest.mark.parametrize('stage,message', [
        ('convert', 'convert settings'),
        ('submit', 'submit the seed'),
    ])
    async def test_broken_stages_raise(self, service, monkeypatch, stage, message):
        monkeypatch.setenv('MOCK_DK64_BROKEN_STAGE', stage)
        with pytest.raises(ValueError, match=message):
            await service._generate_dk64r(None)

    async def test_walks_queued_then_started_then_finished(self, monkeypatch):
        # The progression the presentation layer renders a waiting state from,
        # driven off a controlled clock rather than real seconds.
        from application.utils.mocks import mock_dk64

        monkeypatch.setenv('MOCK_DK64_SECONDS', '100')
        now = [0.0]
        monkeypatch.setattr(mock_dk64.time, 'monotonic', lambda: now[0])

        session = mock_dk64.MockDK64Session()
        async with session.post(
            'https://api.dk64rando.com/api/submit-task',
            json={'settings_data': '{}'},
        ) as resp:
            task_id = (await resp.json())['task_id']

        async def status_at(elapsed):
            now[0] = elapsed
            async with session.get(f'https://api.dk64rando.com/api/task-status/{task_id}') as r:
                return (await r.json())['status']

        assert await status_at(1.0) == 'queued'
        assert await status_at(50.0) == 'started'
        assert await status_at(101.0) == 'finished'

    async def test_stuck_outcome_never_finishes(self, monkeypatch):
        from application.utils.mocks import mock_dk64

        monkeypatch.setenv('MOCK_DK64_SECONDS', '10')
        monkeypatch.setenv('MOCK_DK64_OUTCOME', 'stuck')
        now = [0.0]
        monkeypatch.setattr(mock_dk64.time, 'monotonic', lambda: now[0])

        session = mock_dk64.MockDK64Session()
        async with session.post(
            'https://api.dk64rando.com/api/submit-task', json={'settings_data': '{}'},
        ) as resp:
            task_id = (await resp.json())['task_id']

        now[0] = 100_000.0
        async with session.get(f'https://api.dk64rando.com/api/task-status/{task_id}') as r:
            assert (await r.json())['status'] == 'started'

    async def test_unknown_task_id_is_404(self):
        from application.utils.mocks.mock_dk64 import MockDK64Session

        session = MockDK64Session()
        async with session.get('https://api.dk64rando.com/api/task-status/nope') as resp:
            assert resp.status == 404

    async def test_presets_match_the_upstream_shape(self):
        from application.utils.mocks.mock_dk64 import mock_dk64_presets

        presets = mock_dk64_presets('stable')
        assert presets
        assert all(
            set(p) == {'branch', 'name', 'description', 'settings_string'}
            for p in presets
        )
        assert all(p['branch'] == 'stable' for p in presets)

    def test_refused_in_production(self, monkeypatch):
        from application.utils.mocks.mock_dk64 import is_mock_dk64

        monkeypatch.setenv('ENVIRONMENT', 'production')
        with pytest.raises(RuntimeError, match='must not be enabled in production'):
            is_mock_dk64()


class TestDk64rSpoilerLog:
    """Spoiler logs are forced off, whatever the preset says.

    Upstream serves the log to anyone holding the seed number
    (``GET /get_spoiler_log?hash=<seed_number>``), and the seed number is the
    permalink the players are DMed — so a preset with this on would hand every
    racer the item locations.
    """

    async def test_full_json_preset_asking_for_a_spoiler_is_overridden(
        self, service, monkeypatch, dk64r_key,
    ):
        stub = _DK64RStub([
            (200, {'task_id': 't1', 'status': 'queued'}),
            (200, {'status': 'finished', 'result': {'seed_number': 1}}),
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        preset = _preset({'krool_phases': 3, 'generate_spoilerlog': True})
        rolled = await service._generate_dk64r(preset)

        import json as _json
        sent = _json.loads(stub.calls[0][2]['json']['settings_data'])
        assert sent['generate_spoilerlog'] is False
        # And the recorded snapshot reflects what actually went upstream.
        assert rolled.settings['generate_spoilerlog'] is False

    async def test_converted_settings_string_is_overridden(
        self, service, monkeypatch, dk64r_key,
    ):
        # The live API converts several of the site's own presets — including
        # "Season 5 Race Settings" — with the spoiler log switched on, so the
        # override has to happen after convert_settings, not before.
        stub = _DK64RStub([
            (200, {'krool_phases': 3, 'generate_spoilerlog': True}),   # convert
            (200, {'task_id': 't1', 'status': 'queued'}),
            (200, {'status': 'finished', 'result': {'seed_number': 2}}),
        ])
        import aiohttp
        monkeypatch.setattr(aiohttp, 'ClientSession', stub)
        monkeypatch.setattr('asyncio.sleep', _noop_sleep)

        await service._generate_dk64r(_preset({'settings_string': 'abc'}))

        import json as _json
        sent = _json.loads(stub.calls[1][2]['json']['settings_data'])
        assert sent['generate_spoilerlog'] is False
