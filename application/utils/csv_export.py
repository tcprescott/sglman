"""CSV export helper for report tables."""

import csv
import io
from datetime import datetime
from typing import Iterable, Mapping, Sequence


def rows_to_csv_bytes(
    columns: Sequence[Mapping],
    rows: Iterable[Mapping],
) -> bytes:
    """Render a list of NiceGUI-style column descriptors + row dicts as CSV bytes.

    Each column should have at least ``name`` (key into row dict) and ``label``
    (header text). Hidden columns (``hidden=True``) are skipped.
    """
    visible_columns = [c for c in columns if not c.get('hidden')]
    fields = [c['name'] for c in visible_columns]
    headers = [c.get('label', c['name']) for c in visible_columns]

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_safe_cell(row.get(field, '')) for field in fields])
    return buffer.getvalue().encode('utf-8-sig')


def timestamped_filename(prefix: str, ext: str = 'csv') -> str:
    """``prefix-20251130T143015Z.csv`` style filename."""
    stamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    return f'{prefix}-{stamp}.{ext}'


_FORMULA_PREFIXES = ('=', '+', '-', '@')


def _csv_safe_cell(value) -> str:
    s = _stringify(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return s
    if not s:
        return s
    stripped = s.lstrip(' \t\r\n')
    if stripped and stripped[0] in _FORMULA_PREFIXES:
        return "'" + s
    return s


def _stringify(value) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
