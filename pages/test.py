from nicegui import ui, events, app
import nicegui.elements.table

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
            tabledata = await get_table_data()
            # Emit an event to notify other viewers
            for client in app.clients('/test'):
                with client:
                    # Notify other clients about the deletion
                    ui.notify(f"Row {row_id} deleted")
                    # Find the client's table element
                    client_table = next(
                        (element for element in client.elements.values() if isinstance(element, nicegui.elements.table.Table)),
                        None
                    )
                    if client_table:
                        client_table.rows = tabledata
                        client_table.update()

            # table.rows = tabledata
            # table.update()

        async def refresh_table() -> None:
            table.rows = await get_table_data()
            ui.notify('Refreshed table')
            table.update()
        ui.label(f'Hello {app.storage.user.get("username", "Guest")}!').classes('text-2xl')
        rows = await TestModel.all()
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
            # title='main-table'
        )
        table.add_slot(f'body-cell-actions', """
            <q-td :props="props">
                <q-btn @click="$parent.$emit('roll', props)" icon="casino" flat />
            </q-td>
        """)
        with table.add_slot('top-right'):
            ui.button(on_click=refresh_table, icon='refresh').props('flat')
            ui.button('Add Row (test)', on_click=add_row).props('flat')
        with table.add_slot('top-left'):
            # label = ui.label()
            ui.timer(60, refresh_table)
        # table.on('delete', delete_row)

        # create a button to perform an action on a row when clicked
        table.on('roll', delete_row)