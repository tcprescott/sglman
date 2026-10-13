from dataclasses import dataclass
from html import escape
from typing import Optional, Sequence

from nicegui import ui


def menu_action(icon: str, label: str, on_click, negative: bool = False) -> ui.menu_item:
    """One icon-and-label row inside a ``ui.menu()``; ``negative`` for a destructive one."""
    with ui.menu_item(on_click=on_click).classes('text-negative' if negative else '') as item:
        with ui.item_section().props('avatar'):
            ui.icon(icon)
        ui.item_section(label)
    return item


def more_menu(name: str) -> ui.menu:
    """A row's ⋮ button named "More for <name>"; enter the returned menu to add items."""
    button = ui.button(icon='more_vert', color=None).props('flat round dense').classes('text-grey-7')
    button.props['aria-label'] = f'More for {name}'
    with button:
        menu = ui.menu().props('anchor="bottom right" self="top right"')
    return menu


@dataclass(frozen=True)
class SlotItem:
    """One item of a slot-template ⋮ menu: emits ``event`` with the row."""
    icon: str
    label: str
    event: str
    negative: bool = False
    v_if: Optional[str] = None


def slot_more_menu(name_expr: str, items: Sequence[SlotItem], *, extra_class: str = '') -> str:
    """A row's ⋮ menu for a ``ui.table`` slot, named ``'More for ' + <name_expr>``.

    Destructive items go last under one separator, so pass them last; the
    separator shows whenever any of them does.
    """
    def item_html(it: SlotItem) -> str:
        cond = f' v-if="{escape(it.v_if)}"' if it.v_if else ''
        cls = ' class="text-negative"' if it.negative else ''
        return (
            f'<q-item{cond} clickable{cls} @click="$parent.$emit(\'{it.event}\', props.row)">'
            f'<q-item-section avatar><q-icon name="{it.icon}"/></q-item-section>'
            f'<q-item-section>{escape(it.label)}</q-item-section></q-item>'
        )

    plain = [it for it in items if not it.negative]
    negative = [it for it in items if it.negative]
    body = ''.join(item_html(it) for it in plain)
    if negative:
        conds = [it.v_if for it in negative]
        sep_if = '' if not plain or None in conds else ' v-if="' + escape(' || '.join(f'({c})' for c in conds)) + '"'
        body += (f'<q-separator{sep_if}/>' if plain else '') + ''.join(item_html(it) for it in negative)
    return (
        f'<q-btn flat round dense icon="more_vert" color="grey-7" class="{extra_class}"\n'
        f'       :aria-label="\'More for \' + {name_expr}">'
        '<q-menu auto-close anchor="bottom right" self="top right">'
        f'<q-list style="min-width: 200px">{body}</q-list></q-menu></q-btn>'
    )


def slot_row_button(label: str, icon: str, event: str, *, color: str = 'primary',
                    v_if: Optional[str] = None, extra_class: str = '') -> str:
    """The one labelled button a ``ui.table`` row shows beside its ⋮."""
    cond = f' v-if="{escape(v_if)}"' if v_if else ''
    return (
        f'<q-btn{cond} flat dense no-caps no-wrap color="{color}" icon="{icon}" label="{escape(label)}"'
        f' class="{extra_class}" @click="$parent.$emit(\'{event}\', props.row)" />'
    )


def slot_name_link(field: str, event: str) -> str:
    """A row's name as a link that opens it (emits ``event`` with the row)."""
    return (
        f'<a href="#" class="table-link" @click.prevent="$parent.$emit(\'{event}\', props.row)">'
        f'{{{{ props.row.{field} }}}}</a>'
    )
