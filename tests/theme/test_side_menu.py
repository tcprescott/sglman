"""Side menu helpers: hub entries, starting open state, bottom bar names."""

from theme.side_menu import SHORT_NAMES, NavEntry, default_open_sections, entries_from_tabs


def test_entries_use_the_tab_slug_under_the_hub():
    entries = entries_from_tabs('admin', [
        {'label': 'Admin Schedule', 'slug': 'schedule', 'icon': 'schedule', 'group': 'Operations'},
        {'label': 'Vol. Roster', 'icon': 'groups'},
    ])
    assert [e.path for e in entries] == ['/admin/schedule', '/admin/vol-roster']
    assert entries[0].group == 'Operations'
    assert entries[1].group is None


def test_the_admin_schedule_keeps_its_old_url():
    # DMs, reports and help screenshots link /admin/schedule; the rename is label-only.
    import inspect

    import pages.admin as admin
    assert "'label': 'Admin Schedule', 'slug': 'schedule'" in inspect.getsource(admin)


def test_nothing_is_open_off_a_hub_page():
    assert default_open_sections(None, None) == set()


def test_the_current_hub_and_group_start_open():
    assert default_open_sections('home', None) == {'home'}
    assert default_open_sections('admin', 'Operations') == {'admin', 'admin:Operations'}


def test_long_labels_get_a_short_bottom_bar_name():
    assert NavEntry('/admin/schedule', 'Admin Schedule', 'schedule').short == 'Adm Schd'
    assert NavEntry('/home/event', 'Event', 'event').short == 'Event'


def test_short_names_fit_the_bar():
    # Five tabs share a 360px phone; past nine characters a label wraps.
    for label, short in SHORT_NAMES.items():
        assert len(short) <= 9, (label, short)
        assert len(short) < len(label), label
