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


class TestOotrCode:
    def test_reads_file_hash_from_the_settings_log(self):
        details = {'settingsLog': {'file_hash': ['Deku Stick', 'Bow', 'Boss Key', 'Map', 'Compass']}}
        assert codes.ootr_code(details) == ['Deku Stick', 'Bow', 'Boss Key', 'Map', 'Compass']

    @pytest.mark.parametrize('details', [None, {}, {'settingsLog': None}, {'settingsLog': {'file_hash': []}}])
    def test_missing_log(self, details):
        assert codes.ootr_code(details) is None


class TestSeedDm:
    def test_code_line(self):
        assert seed_code_line(['Bow', 'Lamp']) == 'Code: Bow · Lamp'
        assert seed_code_line(None) == ''

    def test_dm_puts_the_code_under_the_seed(self):
        text = seed_dm('Ann', 'ALTTPR', 'https://alttpr.com/h/x', code_line='Code: Bow · Lamp')
        assert 'https://alttpr.com/h/x\nCode: Bow · Lamp' in text
