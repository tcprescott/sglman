"""A type-to-filter multi-select whose options can carry a colour dot and a caption.

Built for pickers with dozens of entries (a Discord server's roles, every grant
an app role mapping can hand out): typing narrows the list, chips show what is
picked, and each option can say something about itself ("already grants Staff")
without that text leaking into the filter match.
"""

from typing import Any, Mapping, Optional

from nicegui import ui

_OPTION_SLOT = '''
<q-item v-bind="props.itemProps">
    <q-item-section side v-if="props.opt.color !== undefined" class="q-pr-sm">
        <q-icon name="circle" size="xs" :style="{color: props.opt.color}" />
    </q-item-section>
    <q-item-section>
        <q-item-label>{{ props.opt.label }}</q-item-label>
        <q-item-label caption v-if="props.opt.caption">{{ props.opt.caption }}</q-item-label>
    </q-item-section>
    <q-item-section side>
        <q-icon :name="props.selected ? 'check_box' : 'check_box_outline_blank'"
                :color="props.selected ? 'primary' : 'grey'" />
    </q-item-section>
</q-item>
'''

_CHIP_SLOT = '''
<q-chip dense removable :tabindex="props.tabindex" @remove="props.removeAtIndex(props.index)">
    <q-icon v-if="props.opt.color !== undefined" name="circle" size="xs"
            class="q-mr-xs" :style="{color: props.opt.color}" />
    {{ props.opt.label }}
</q-chip>
'''


class FilterMultiSelect(ui.select):
    """``ui.select(multiple=True, with_input=True)`` with per-option colour and caption.

    ``extras`` maps an option *key* to ``{'color': css, 'caption': str}``; either
    may be omitted. NiceGUI regenerates the option dicts on every ``update()``
    and rebuilds the selected values from bare ``{value, label}`` pairs, so both
    hooks are overridden to carry the extras through; patching ``props`` once
    would be wiped by the next selection.
    """

    def __init__(
        self,
        options: Mapping[Any, str],
        *,
        label: str,
        extras: Optional[Mapping[Any, Mapping[str, str]]] = None,
    ) -> None:
        self._extras = dict(extras or {})
        super().__init__(
            options=dict(options), label=label, multiple=True, with_input=True, value=[],
        )
        self.props('use-chips stack-label options-dense')
        self.add_slot('option', _OPTION_SLOT)
        self.add_slot('selected-item', _CHIP_SLOT)

    def _decorate(self, option: dict) -> dict:
        extra = self._extras.get(self._values[option['value']])
        return {**option, **extra} if extra else option

    def _update_options(self) -> None:
        super()._update_options()
        self._props['options'] = [self._decorate(o) for o in self._props['options']]

    def _value_to_model_value(self, value: Any) -> Any:
        return [self._decorate(o) for o in super()._value_to_model_value(value)]


def bulk_add_summary(new: int, existing: int, *, empty_hint: str) -> str:
    """The "what Add will do" line under a many-to-many add dialog."""
    if not new and not existing:
        return empty_hint
    if not new:
        return 'All of these already exist.' if existing > 1 else 'That mapping already exists.'
    text = f"Adds {new} mapping{'' if new == 1 else 's'}"
    if existing:
        text += f"; {existing} already {'exists' if existing == 1 else 'exist'} and will be skipped"
    return text + '.'
