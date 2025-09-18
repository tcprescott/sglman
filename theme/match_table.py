from nicegui import ui

class MatchTable:
    def __init__(self, columns, rows=None, admin_controls=None):
        self.columns = columns
        self.rows = rows if rows is not None else []
        self.admin_controls = admin_controls
        self.table = None

    def render(self):
        # Add custom CSS for vertical lines between columns
        ui.add_head_html("""
        <style>
        .match-table th, .match-table td {
            border-right: 1px solid #ccc;
        }
        .match-table td {
            text-align: left;
        }
        .match-table th {
            text-align: center;
        }
        .match-table th:last-child, .match-table td:last-child {
            border-right: none;
        }
        .match-table {
            border-collapse: collapse;
        }
        .match-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .match-table tr:nth-child(odd) {
            background-color: #ffffff;
        }
        </style>
        """)
        with ui.column().style('width: 100%;'):
            self.table = ui.table(
                columns=self.columns,
                rows=self.rows,
                row_key='id'
            ).classes('match-table').style('margin-top: 1em; width: 100%;')

        return self.table
