from nicegui import ui

class MatchTable:
    def __init__(self, columns, rows=None, admin_controls=None):
        self.columns = columns
        self.rows = rows if rows is not None else []
        self.admin_controls = admin_controls
        self.table = None

    def render(self):
        with ui.column().style('width: 100%;'):
            if self.admin_controls:
                with ui.row().style('width: 100%;'):
                    for control in self.admin_controls:
                        control()
            self.table = ui.table(
                columns=self.columns,
                rows=self.rows,
                row_key='id'
            ).style('margin-top: 1em; width: 100%;')
        return self.table
