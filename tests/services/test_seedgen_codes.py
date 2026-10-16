"""Tests for the seed-code readers (unit, no network)."""

import pytest

import application.services._seedgen_codes as codes
from application.utils.discord_messages import seed_code_line, seed_dm


class TestAlttprCode:
    def test_reads_the_five_bytes_at_the_code_offset(self):
        patch = [{str(0x180210): [9, 9, 9, 9, 9, 0, 2, 3, 11, 20, 9]}]
        assert codes.alttpr_code(patch) == ['Bow', 'Hookshot', 'Bombs', 'Lamp', 'Cape']

    @pytest.mark.parametrize('patch', [None, [], [{'5': [1, 2]}], [{str(0x180215): [1, 2]}],
                                       [{str(0x180215): [1, 2, 3, 4, 99]}]])
    def test_no_code_rather_than_a_wrong_one(self, patch):
        assert codes.alttpr_code(patch) is None


class TestDk64rCode:
    def test_maps_digits_to_icon_names(self):
        assert codes.dk64r_code([0, 9, 5, 2, 7]) == [
            'Bongos', 'Saxophone', 'Nintendo Coin', 'DK Coin', 'Rainbow Coin',
        ]

    @pytest.mark.parametrize('digits', [None, [], [1, 10], ['1']])
    def test_rejects_anything_else(self, digits):
        assert codes.dk64r_code(digits) is None


class TestWordCodes:
    def test_map_rando_splits_its_hash(self):
        assert codes.smmap_code('VIOLA WAVER SOVA GEEMER') == ['VIOLA', 'WAVER', 'SOVA', 'GEEMER']

    @pytest.mark.parametrize('value', [None, '', 'ONE', 7])
    def test_map_rando_without_a_hash(self, value):
        assert codes.smmap_code(value) is None

    def test_dash_reads_the_escaped_next_payload(self):
        html = r'<script>self.__next_f.push([1,"{\"signature\":\"VIOLA WAVER SOVA GEEMER\",\"slug\":\"x\"}"])</script>'
        assert codes.dash_code_from_page(html) == ['VIOLA', 'WAVER', 'SOVA', 'GEEMER']

    def test_dash_page_without_a_signature(self):
        assert codes.dash_code_from_page('<html></html>') is None


_OOTR_PAGE = (
    'settingsRaw = "{\\n  \\":version\\":   \\"9.1.38 f.LUM\\",\\n  \\"file_hash\\":    '
    '[\\"SOLD OUT\\", \\"Mirror Shield\\", \\"Bombchu\\", \\"Heart Container\\", \\"Mask of Truth\\"],'
    '\\n  \\":seed\\": \\"KHSZ0TRAGO\\"}";'
)
_OOTR_CODE = ['SOLD OUT', 'Mirror Shield', 'Bombchu', 'Heart Container', 'Mask of Truth']


class _FakeResponse:
    def __init__(self, status, body):
        self.status, self._body = status, body

    async def json(self, content_type=None):
        return self._body

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _fake_ootr(monkeypatch, statuses, page):
    """Answer the status endpoint from ``statuses`` in turn, then the seed page."""
    calls = []
    statuses = list(statuses)

    def request(method, url, params=None, timeout=None):
        calls.append(url)
        if isinstance(page, Exception) and url.endswith('/seed/get'):
            raise page
        if url.endswith('/seed/status'):
            return _FakeResponse(*statuses.pop(0))
        return _FakeResponse(*page)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(codes.aiohttp, 'request', request)
    monkeypatch.setattr(codes.asyncio, 'sleep', no_sleep)
    return calls


class TestOotrCode:
    def test_reads_file_hash_from_the_seed_page(self):
        assert codes.ootr_code_from_page(_OOTR_PAGE) == _OOTR_CODE

    @pytest.mark.parametrize('html', [None, '', '<html></html>', '"file_hash": []'])
    def test_page_without_a_code(self, html):
        assert codes.ootr_code_from_page(html) is None

    async def test_waits_for_generation_then_reads_the_page(self, monkeypatch):
        calls = _fake_ootr(monkeypatch, [(200, {'status': 0}), (204, None), (200, {'status': 1})],
                           (200, _OOTR_PAGE))
        assert await codes.fetch_ootr_code('1', 'k') == _OOTR_CODE
        assert calls[-1] == 'https://ootrandomizer.com/seed/get'
        assert sum(u.endswith('/seed/status') for u in calls) == 3

    @pytest.mark.parametrize('statuses,page', [
        ([(200, {'status': 2})], (200, _OOTR_PAGE)),
        ([(403, 'Invalid API Key')], (200, _OOTR_PAGE)),
        ([(200, {'status': 1})], (500, 'oops')),
        ([(200, {'status': 1})], (200, '<html>redesigned</html>')),
    ])
    async def test_a_miss_logs_an_error_and_gives_no_code(self, monkeypatch, caplog, statuses, page):
        _fake_ootr(monkeypatch, statuses, page)
        assert await codes.fetch_ootr_code('1', 'k') is None
        assert any(r.levelname == 'ERROR' and 'OoTR seed code unavailable' in r.message
                   for r in caplog.records)

    async def test_gives_up_when_the_seed_never_finishes(self, monkeypatch, caplog):
        monkeypatch.setattr(codes, 'OOTR_GENERATION_WAIT_SECONDS', 0)
        _fake_ootr(monkeypatch, [(200, {'status': 0})], (200, _OOTR_PAGE))
        assert await codes.fetch_ootr_code('1', 'k') is None
        assert 'still generating' in caplog.text

    async def test_network_error_never_raises(self, monkeypatch, caplog):
        _fake_ootr(monkeypatch, [(200, {'status': 1})], codes.aiohttp.ClientConnectionError('down'))
        assert await codes.fetch_ootr_code('1', 'k') is None
        assert 'OoTR seed code unavailable' in caplog.text


class TestSeedDm:
    def test_code_line(self):
        assert seed_code_line(['Bow', 'Lamp']) == 'Code: Bow · Lamp'
        assert seed_code_line(None) == ''

    def test_dm_puts_the_code_under_the_seed(self):
        text = seed_dm('Ann', 'ALTTPR', 'https://alttpr.com/h/x', code_line='Code: Bow · Lamp')
        assert 'https://alttpr.com/h/x\nCode: Bow · Lamp' in text
