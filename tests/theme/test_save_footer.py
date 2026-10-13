"""A settings card's Save bar: Discard puts the fields back, and the page knows what's unsaved."""

import asyncio

import pytest
from nicegui import ui
from nicegui.client import Client
from nicegui.page import page

from theme.save_footer import SaveFooter, UnsavedChanges


@pytest.fixture
def slot():
    with Client(page('/')):
        yield


def test_discard_restores_the_watched_values(slot):
    field = ui.input(value='old')
    footer = SaveFooter(lambda: None).watch(field)
    field.value = 'new'
    assert footer.dirty
    footer.discard()
    assert field.value == 'old'
    assert not footer.dirty
    assert not footer.row.visible


def test_a_save_moves_the_discard_point(slot):
    field = ui.input(value='old')

    async def save() -> bool:
        return True

    footer = SaveFooter(save).watch(field)
    field.value = 'new'
    assert asyncio.run(footer.save())
    field.value = 'newer'
    footer.discard()
    assert field.value == 'new'


def test_a_refused_save_stays_dirty(slot):
    field = ui.input(value='old')

    async def save() -> bool:
        return False

    footer = SaveFooter(save).watch(field)
    field.value = 'new'
    assert not asyncio.run(footer.save())
    assert footer.dirty


def test_the_group_tracks_its_dirty_footers(slot):
    changes: list[int] = []
    unsaved = UnsavedChanges(on_change=lambda: changes.append(len(unsaved.dirty())))
    with unsaved.collect():
        first = ui.input(value='a')
        SaveFooter(lambda: None).watch(first)
        second = ui.input(value='b')
        SaveFooter(lambda: None).watch(second)
    outside = ui.input(value='c')
    SaveFooter(lambda: None).watch(outside)

    first.value = 'changed'
    outside.value = 'changed'
    assert len(unsaved.dirty()) == 1
    assert changes == [1]


def test_a_read_only_card_never_goes_dirty(slot):
    field = ui.input(value='old')
    footer = SaveFooter(lambda: None, enabled=False).watch(field)
    field.value = 'new'
    assert not footer.dirty
