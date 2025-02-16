from nicegui import ui, events
from theme import theme

from models import TestModel

def create() -> None:
    @ui.page('/test')
    async def test():
        async def get_table_data():
            rows = await TestModel.all()
            return [
                {
                    'id': row.id,
                    'name': row.name,
                    'description': row.description,
                    'value': row.value,
                    'somethingelse': row.somethingelse,
                } for row in rows]

        async def add_row() -> None:
            row = await TestModel.create(name='Test', description='Test', value=1, somethingelse='Test')
            ui.notify(f'Added row {row.id}')
            table.rows = await get_table_data()
            table.update()

        async def delete_row(e: events.GenericEventArguments) -> None:
            row_id = e.args['key']
            await TestModel.filter(id=row_id).delete()
            ui.notify(f"Deleted row {row_id}")
            table.rows = await get_table_data()
            table.update()

        async def refresh_table() -> None:
            table.rows = await get_table_data()
            ui.notify('Refreshed table')
            table.update()

        rows = await TestModel.all()
        with theme.frame('Home'):
            table = ui.table(
                columns=[
                    {'name': 'name', 'label': 'Name', 'field': 'name'},
                    {'name': 'description', 'label': 'Description', 'field': 'description'},
                    {'name': 'value', 'label': 'Value', 'field': 'value'},
                    {'name': 'somethingelse', 'label': 'Something Else', 'field': 'somethingelse'},
                    {'name': 'actions', 'label': 'Actions'},
                ],
                rows=await get_table_data(),
                row_key='id',
            )
            table.add_slot(f'body-cell-actions', """
                <q-td :props="props">
                    <q-btn @click="$parent.$emit('roll', props)" icon="casino" flat />
                </q-td>
            """)
            with table.add_slot('top-right'):
                ui.button(on_click=refresh_table, icon='refresh').props('flat')
            with table.add_slot('top-left'):
                # label = ui.label()
                ui.timer(60, refresh_table)
            # table.on('delete', delete_row)

            # create a button to perform an action on a row when clicked
            table.on('roll', delete_row)