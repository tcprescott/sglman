"""Tests for the backends ported from SahasrahBot: AVIANART, samus.link (SM, SMZ3),
Zelda 2, SMB3R and Aria of Sorrow (unit — no network)."""

import urllib.parse

import pytest

import application.services._seedgen_avianart as avianart
from application.services._seedgen_codes import avianart_code, mock_code, samus_code
from application.services.preset_service import PresetService
from application.services.seedgen_service import SeedGenerationService
from application.utils.seed_provider import (
    SeedProviderBadResponse,
    SeedProviderInvalidRequest,
)
from models import Preset


@pytest.fixture
def service(monkeypatch):
    monkeypatch.delenv('MOCK_SEEDGEN', raising=False)
    return SeedGenerationService()


def _preset(randomizer, settings):
    return Preset(name='p', randomizer=randomizer, settings=settings)


class _FakeResp:
    def __init__(self, body, status=200):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        return self._body

    async def text(self):
        return str(self._body)


class _FakeSession:
    """Answers ``post`` with ``started`` and each ``get`` with the next poll body."""

    def __init__(self, started, polls):
        self.started = started
        self.polls = list(polls)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, **kwargs):
        self.calls.append(('post', url, kwargs))
        return _FakeResp(self.started)

    def get(self, url, **kwargs):
        self.calls.append(('get', url, kwargs))
        return _FakeResp(self.polls.pop(0))


@pytest.fixture
def avianart_upstream(monkeypatch):
    import aiohttp

    async def _no_sleep(_):
        return None

    monkeypatch.setattr(avianart.asyncio, 'sleep', _no_sleep)
    holder = {}

    def _install(started, polls):
        session = _FakeSession(started, polls)
        holder['session'] = session
        monkeypatch.setattr(aiohttp, 'ClientSession', lambda *a, **k: session)
        return session

    return _install


_STARTED = {'status': 200, 'response': {'status': 'generating', 'hash': 'r4oVJztfd'}}
_VT_DONE = {'status': 200, 'response': {
    'hash': '0yAOb48PMV', 'fshash': 'Magic Powder, Flute, Book, Flippers, Bombos', 'type': 'dr',
}}


class TestAvianart:
    async def test_rolls_a_race_seed_and_waits_for_it(self, service, avianart_upstream):
        session = avianart_upstream(_STARTED, [
            {'status': 200, 'response': {'status': 'generating', 'hash': 'r4oVJztfd'}},
            _VT_DONE,
        ])
        call = await service.generate_seed_call('avianart', _preset('avianart', {'preset': 'open'}))
        assert call.value.url == 'https://avianart.games/perm/r4oVJztfd'
        assert call.value.settings == {'preset': 'open', 'race': True}
        assert call.value.code == ['Magic Powder', 'Flute', 'Book', 'Flippers', 'Bombos']
        method, _, sent = session.calls[0]
        assert method == 'post'
        assert sent['params'] == {'action': 'generate', 'preset': 'open'}
        assert sent['json'] == [{'args': {'race': True}}]
        assert [c[2]['params'] for c in session.calls[1:]] == [
            {'action': 'permlink', 'hash': 'r4oVJztfd'},
        ] * 2

    def test_rolls_once_because_every_generate_builds_a_game(self):
        assert SeedGenerationService.PROVIDER_ATTEMPTS['avianart'] == 1

    async def test_a_failed_build_names_the_preset(self, service, avianart_upstream):
        avianart_upstream(_STARTED, [
            {'status': 200, 'response': {'status': 'failure', 'message': 'Failed to generate'}},
        ])
        with pytest.raises(SeedProviderInvalidRequest, match='nosuch'):
            await service.generate_seed('avianart', _preset('avianart', {'preset': 'nosuch'}))

    async def test_gives_up_when_it_never_finishes(self, service, avianart_upstream, monkeypatch):
        monkeypatch.setattr(avianart, 'AVIANART_MAX_POLLS', 2)
        generating = {'status': 200, 'response': {'status': 'generating'}}
        avianart_upstream(_STARTED, [generating, generating])
        with pytest.raises(SeedProviderBadResponse, match='still building'):
            await service.generate_seed('avianart', _preset('avianart', {'preset': 'open'}))

    async def test_no_hash_means_no_seed(self, service, avianart_upstream):
        avianart_upstream({'status': 200, 'response': {'status': 'error', 'message': 'Queue full'}}, [])
        with pytest.raises(SeedProviderBadResponse, match='Queue full'):
            await service.generate_seed('avianart', _preset('avianart', {'preset': 'open'}))

    @pytest.mark.parametrize('settings', [None, {}, {'preset': ''}, {'preset': '../x'}, {'preset': 'a', 'b': 1}])
    async def test_refuses_a_bad_preset_before_calling_upstream(self, service, settings):
        preset = _preset('avianart', settings) if settings is not None else None
        with pytest.raises(SeedProviderInvalidRequest):
            await service.generate_seed('avianart', preset)

    def test_accepts_a_user_preset(self):
        assert SeedGenerationService.normalize_preset_settings(
            'avianart', {'preset': ' kaesden/casualboots '},
        ) == {'preset': 'kaesden/casualboots'}

    async def test_catalogue_becomes_presets(self, service, monkeypatch):
        import aiohttp

        body = {'status': 200, 'response': {'modes': [
            {'prefix': 'crosskeys', 'name': 'Crosskeys', 'description': 'Keys everywhere.'},
            {'prefix': 'open', 'name': 'Open', 'description': None},
            {'prefix': 'bad name', 'name': 'Skipped'},
        ]}}
        monkeypatch.setattr(aiohttp, 'request', lambda **kw: _FakeResp(body))
        presets = await service.list_remote_presets('avianart')
        assert [(p.name, p.settings, p.description) for p in presets] == [
            ('crosskeys', {'preset': 'crosskeys'}, 'Crosskeys. Keys everywhere.'),
            ('open', {'preset': 'open'}, 'Open'),
        ]
        assert SeedGenerationService.offers_remote_presets('avianart')
        assert SeedGenerationService.remote_preset_branches('avianart') == []


class TestAvianartCode:
    def test_plain_presets_send_fshash(self):
        assert avianart_code(_VT_DONE['response']) == [
            'Magic Powder', 'Flute', 'Book', 'Flippers', 'Bombos',
        ]

    def test_door_presets_put_it_in_the_spoiler_with_short_names(self):
        result = {'spoiler': {'meta': {'hash': 'Hookshot, Powder, Rod, Tunic, Shovel'}}}
        assert avianart_code(result) == ['Hookshot', 'Magic Powder', 'Ice Rod', 'Tunic', 'Shovel']

    @pytest.mark.parametrize('result', [None, {}, {'fshash': 'Bow, Hookshot'}, {'spoiler': {'meta': {'hash': None}}}])
    def test_anything_else_is_no_code(self, result):
        assert avianart_code(result) is None


@pytest.fixture
def samus_upstream(monkeypatch):
    import aiohttp

    calls = []
    body = {'guid': 'd835ba9637844a71b337ebfe0d4b6797', 'hash': 'RIPPER HOLTZ ATOMIC CHOOT'}

    def _request(**kwargs):
        calls.append(kwargs)
        return _FakeResp(body)

    monkeypatch.setattr(aiohttp, 'request', _request)
    return calls


class TestSamusLink:
    @pytest.mark.parametrize('randomizer, base', [
        ('sm', 'https://sm.samus.link'), ('smz3', 'https://samus.link'),
    ])
    async def test_rolls_a_race_seed_from_the_preset(self, service, samus_upstream, randomizer, base):
        preset = _preset(randomizer, {'logic': 'tournament', 'seed': '123', 'spoilerKey': 'leak', 'race': 'false'})
        call = await service.generate_seed_call(randomizer, preset)
        assert call.value.url == f'{base}/seed/2DW6ljeESnGzN-v-DUtnlw'
        assert call.value.code == ['RIPPER', 'HOLTZ', 'ATOMIC', 'CHOOT']
        sent = samus_upstream[0]
        assert sent['url'] == f'{base}/api/randomizers/{randomizer}/generate'
        assert sent['json'] == {'logic': 'tournament', 'seed': '', 'race': 'true'}
        assert call.value.settings == sent['json']

    async def test_needs_a_preset(self, service):
        with pytest.raises(SeedProviderInvalidRequest, match='Super Metroid needs a preset'):
            await service.generate_seed('sm', None)

    async def test_no_guid_is_a_bad_response(self, service, monkeypatch):
        import aiohttp

        monkeypatch.setattr(aiohttp, 'request', lambda **kw: _FakeResp({'error': 'nope'}))
        with pytest.raises(SeedProviderBadResponse):
            await service.generate_seed('smz3', _preset('smz3', {'smlogic': 'normal'}))

    def test_nested_settings_are_refused(self):
        with pytest.raises(ValueError, match='flat object'):
            SeedGenerationService.normalize_preset_settings('smz3', {'a': {'b': 1}})

    def test_code_is_four_words(self):
        assert samus_code('GIBO ZEELA TATORI ROPA') == ['GIBO', 'ZEELA', 'TATORI', 'ROPA']
        assert samus_code(None) is None


class TestFlagGames:
    @pytest.mark.parametrize('randomizer, top', [('z2r', 1000000000), ('smb3r', 999999999999)])
    async def test_seed_number_beside_the_flags(self, service, randomizer, top):
        call = await service.generate_seed_call(randomizer, _preset(randomizer, {'flags': ' iyhq$j9 '}))
        seed, flags = call.value.url.split(' - ')
        assert flags == 'iyhq$j9'
        assert 0 <= int(seed) <= top
        assert call.value.settings == {'seed': seed, 'flags': 'iyhq$j9'}

    @pytest.mark.parametrize('randomizer', ['z2r', 'smb3r'])
    async def test_needs_a_preset(self, service, randomizer):
        with pytest.raises(SeedProviderInvalidRequest, match='needs a preset with flags'):
            await service.generate_seed(randomizer, None)

    def test_flags_with_spaces_are_refused(self):
        with pytest.raises(ValueError, match='Zelda 2 flags are one string'):
            SeedGenerationService.normalize_preset_settings('z2r', {'flags': 'a b'})

    def test_paste_instructions_name_the_game(self):
        assert SeedGenerationService.paste_instructions('smb3r', None) == (
            'Enter this seed and these flags in the Super Mario Bros. 3 Randomizer.'
        )
        assert SeedGenerationService.paste_instructions('z1r', None) == (
            'Enter this seed and these flags in the Zelda 1 Randomizer.'
        )

    def test_example_seed_for_the_presets_tab(self):
        assert SeedGenerationService.example_flag_seed('z2r', 'abc').endswith(' - abc')
        assert SeedGenerationService.rolls_from_flags('z2r')
        assert not SeedGenerationService.rolls_from_flags('aosr')

    async def test_local_rolls_skip_the_mock(self, service, monkeypatch):
        monkeypatch.setenv('ENVIRONMENT', 'development')
        monkeypatch.setenv('MOCK_SEEDGEN', 'true')
        assert ' - ' in await service.generate_seed('z2r', _preset('z2r', {'flags': 'x'}))


class TestAriaOfSorrow:
    async def test_keeps_the_options_and_replaces_the_seed(self, service):
        preset = _preset('aosr', {'url': 'https://aosrando.surge.sh/?seed=5&shopRando=true&empty='})
        call = await service.generate_seed_call('aosr', preset)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(call.value.url).query, keep_blank_values=True)
        assert qs['shopRando'] == ['true']
        assert qs['empty'] == ['']
        assert qs['seed'] != ['5']
        assert -2147483648 <= int(qs['seed'][0]) <= 2147483647

    @pytest.mark.parametrize('url', ['http://aosrando.surge.sh/', 'https://evil.example/?seed=1', ''])
    def test_only_takes_an_aosrando_link(self, url):
        with pytest.raises(ValueError):
            SeedGenerationService.normalize_preset_settings('aosr', {'url': url})


class TestMockAndBuiltins:
    def test_mock_codes_cover_the_upstream_backends(self):
        assert len(mock_code('avianart')) == 5
        assert len(mock_code('sm')) == 4
        assert len(mock_code('smz3')) == 4

    def test_samus_link_builtins_load_without_roll_owned_keys(self):
        entries = [e for e in PresetService._load_builtins() if e['randomizer'] in ('sm', 'smz3')]
        assert {e['randomizer'] for e in entries} == {'sm', 'smz3'}
        for entry in entries:
            assert entry['description']
            assert not {'seed', 'race', 'spoilerKey'} & set(entry['settings'])
            assert SeedGenerationService.normalize_preset_settings(
                entry['randomizer'], entry['settings'],
            ) == entry['settings']
