"""CSV export for any table, not only the reports.

Lifted out of ``pages/admin_tabs/reports/shared.py`` unchanged. It was never a
report detail — "give me these rows in a spreadsheet" is the same request on the
Users board as it is on a crew-hours report — and leaving it there is why only
the reports had it.

Pair it with a customized table by passing the *plan's* columns as the provider
rather than the shipped defaults, so the export matches what the person is
looking at:

    csv_export_button('people', lambda: view._plan.columns, lambda: table.rows)
"""

from typing import Callable, Iterable, Mapping, Sequence

from nicegui import ui

from application.utils.csv_export import rows_to_csv_bytes, timestamped_filename

__all__ = ['csv_export_button']


def csv_export_button(
    filename_prefix: str,
    columns_provider: Callable[[], Sequence[Mapping]],
    rows_provider: Callable[[], Iterable[Mapping]],
    label: str = 'Export CSV',
) -> ui.button:
    """Button that downloads the current rows as CSV when clicked."""

    def _click():
        try:
            data = rows_to_csv_bytes(columns_provider(), rows_provider())
            ui.download(data, filename=timestamped_filename(filename_prefix))
        except Exception as exc:  # pragma: no cover - defensive UI feedback
            ui.notify(f'Export failed: {exc}', color='negative')

    return ui.button(label, icon='download', on_click=_click).props('flat dense')
