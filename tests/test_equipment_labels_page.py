"""Unit tests for the bulk QR-label sheet page helpers."""

from pages.equipment_labels import _parse_ids


class TestParseIds:
    def test_parses_and_orders_input(self):
        assert _parse_ids('3,1,2') == [3, 1, 2]

    def test_drops_blanks_and_non_numerics(self):
        assert _parse_ids('3, ,x,1,,2') == [3, 1, 2]

    def test_empty_inputs(self):
        assert _parse_ids('') == []
        assert _parse_ids('   ') == []
        assert _parse_ids(',,') == []
