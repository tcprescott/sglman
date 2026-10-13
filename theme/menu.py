from nicegui import ui


def menu_action(icon: str, label: str, on_click, negative: bool = False) -> None:
    """One icon-and-label row inside a ``ui.menu()``; ``negative`` for a destructive one."""
    with ui.menu_item(on_click=on_click).classes('text-negative' if negative else ''):
        with ui.item_section().props('avatar'):
            ui.icon(icon)
        ui.item_section(label)
