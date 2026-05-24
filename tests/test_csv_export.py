"""Unit tests for csv_export utility.

The most important behavior to lock in is CSV-injection defense: any cell
whose first non-whitespace character is one of ``= + - @`` must be escaped
so that spreadsheet software does not interpret it as a formula.
"""

from datetime import datetime, timezone

import pytest

from application.utils import csv_export
from application.utils.csv_export import (
    rows_to_csv_bytes,
    timestamped_filename,
    _csv_safe_cell,
    _stringify,
)


def _decode(b: bytes) -> str:
    # Strip BOM if present so we can compare against plain strings.
    return b.decode('utf-8-sig')


# ---------------------------------------------------------------------------
# rows_to_csv_bytes
# ---------------------------------------------------------------------------


class TestRowsToCsvBytes:
    def test_emits_headers_from_label(self):
        columns = [{'name': 'a', 'label': 'Alpha'}, {'name': 'b', 'label': 'Beta'}]
        out = _decode(rows_to_csv_bytes(columns, []))
        assert out.splitlines()[0] == 'Alpha,Beta'

    def test_falls_back_to_name_when_label_missing(self):
        columns = [{'name': 'a'}]
        out = _decode(rows_to_csv_bytes(columns, []))
        assert out.splitlines()[0] == 'a'

    def test_emits_rows_in_order(self):
        columns = [{'name': 'a', 'label': 'A'}, {'name': 'b', 'label': 'B'}]
        rows = [{'a': '1', 'b': '2'}, {'a': '3', 'b': '4'}]
        out = _decode(rows_to_csv_bytes(columns, rows))
        assert out.splitlines() == ['A,B', '1,2', '3,4']

    def test_hidden_columns_are_excluded(self):
        columns = [
            {'name': 'a', 'label': 'A'},
            {'name': 'secret', 'label': 'S', 'hidden': True},
        ]
        rows = [{'a': '1', 'secret': 'leak'}]
        out = _decode(rows_to_csv_bytes(columns, rows))
        assert 'S' not in out
        assert 'leak' not in out
        assert 'A' in out and '1' in out

    def test_missing_row_keys_emit_empty_cells(self):
        columns = [{'name': 'a', 'label': 'A'}, {'name': 'b', 'label': 'B'}]
        rows = [{'a': '1'}]  # no 'b'
        out = _decode(rows_to_csv_bytes(columns, rows))
        # Second row's b cell should be empty
        assert out.splitlines()[1] == '1,'

    def test_output_starts_with_utf8_bom(self):
        # The BOM hint helps Excel recognize UTF-8.
        raw = rows_to_csv_bytes([{'name': 'a', 'label': 'A'}], [])
        assert raw.startswith(b'\xef\xbb\xbf')

    def test_returns_bytes(self):
        assert isinstance(rows_to_csv_bytes([], []), bytes)

    def test_uses_lf_line_terminator(self):
        columns = [{'name': 'a', 'label': 'A'}]
        rows = [{'a': '1'}, {'a': '2'}]
        out = _decode(rows_to_csv_bytes(columns, rows))
        assert '\r\n' not in out
        assert out.count('\n') == 3  # header + 2 rows


# ---------------------------------------------------------------------------
# _csv_safe_cell — formula injection defense
# ---------------------------------------------------------------------------


class TestCsvInjectionEscaping:
    @pytest.mark.parametrize('payload', [
        '=cmd|\' /C calc\'!A0',
        '=1+1',
        '+SUM(A1:A2)',
        '-2+3',
        '@SUM(1,1)',
    ])
    def test_formula_prefixes_are_escaped(self, payload):
        result = _csv_safe_cell(payload)
        assert result.startswith("'"), f"payload {payload!r} not escaped: {result!r}"
        assert result == "'" + payload

    @pytest.mark.parametrize('payload', [
        ' =1+1',
        '\t=1+1',
        '\n=1+1',
        '\r=1+1',
        '  +abc',
    ])
    def test_whitespace_before_formula_is_still_escaped(self, payload):
        # Spreadsheets ignore leading whitespace, so we have to escape these too.
        result = _csv_safe_cell(payload)
        assert result.startswith("'"), f"payload {payload!r} not escaped: {result!r}"

    @pytest.mark.parametrize('payload', [
        'hello',
        '123abc',
        'a=b',  # = is not at the start
        '',
        ' ',  # whitespace-only is not a formula
        'name@example.com',  # @ in the middle is fine
    ])
    def test_benign_strings_are_not_escaped(self, payload):
        result = _csv_safe_cell(payload)
        assert not result.startswith("'"), f"benign payload {payload!r} unexpectedly escaped: {result!r}"

    def test_numeric_int_is_not_escaped(self):
        # Negative numbers stringify with a leading '-' but should keep numeric semantics.
        assert _csv_safe_cell(-5) == '-5'
        assert _csv_safe_cell(0) == '0'
        assert _csv_safe_cell(42) == '42'

    def test_numeric_float_is_not_escaped(self):
        assert _csv_safe_cell(-3.14) == '-3.14'
        assert _csv_safe_cell(1.5) == '1.5'

    def test_bool_strings_used_not_int_path(self):
        # bool is a subclass of int but should serialize as 'true'/'false'
        assert _csv_safe_cell(True) == 'true'
        assert _csv_safe_cell(False) == 'false'

    def test_escaping_appears_in_full_csv_output(self):
        # End-to-end: an injection payload survives escaping through rows_to_csv_bytes.
        columns = [{'name': 'a', 'label': 'A'}]
        payload = "=cmd|' /C calc'!A0"
        out = _decode(rows_to_csv_bytes(columns, [{'a': payload}]))
        # The cell row should be the escaped payload (leading apostrophe before '=').
        # No CSV quoting is triggered here — the payload contains no delimiter,
        # double-quote, or newline — so the line is emitted as a literal.
        assert out.splitlines()[1] == "'" + payload


# ---------------------------------------------------------------------------
# _stringify
# ---------------------------------------------------------------------------


class TestStringify:
    def test_none_returns_empty_string(self):
        assert _stringify(None) == ''

    def test_bool_true(self):
        assert _stringify(True) == 'true'

    def test_bool_false(self):
        assert _stringify(False) == 'false'

    def test_datetime_uses_isoformat(self):
        dt = datetime(2025, 1, 15, 14, 30, tzinfo=timezone.utc)
        assert _stringify(dt) == dt.isoformat()

    def test_other_objects_use_str(self):
        assert _stringify(123) == '123'
        assert _stringify(1.5) == '1.5'
        assert _stringify('abc') == 'abc'


# ---------------------------------------------------------------------------
# timestamped_filename
# ---------------------------------------------------------------------------


class TestTimestampedFilename:
    def test_uses_prefix_and_default_csv_extension(self):
        name = timestamped_filename('report')
        assert name.startswith('report-')
        assert name.endswith('.csv')

    def test_custom_extension(self):
        name = timestamped_filename('report', ext='tsv')
        assert name.endswith('.tsv')

    def test_timestamp_is_compact_iso_z(self, monkeypatch):
        # Pin the clock so we can assert the exact filename.
        class FixedDateTime:
            @classmethod
            def utcnow(cls):
                return datetime(2025, 10, 23, 14, 30, 15)

        monkeypatch.setattr(csv_export, 'datetime', FixedDateTime)
        assert timestamped_filename('peak') == 'peak-20251023T143015Z.csv'
