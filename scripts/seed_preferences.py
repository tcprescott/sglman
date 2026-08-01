"""Seed per-user table layouts.

Global fixtures, like the model itself: ``UserTablePreference`` carries no tenant
column, so this runs once beside ``seed_users`` rather than per community.

One saved layout per shape the reconciler has to handle — a hidden column, a
reordered list, a stored width, and a non-default page size — so the
``/ui-validation`` loop exercises the *applied* path. Without these, every dev
run only ever sees the defaults, which is the path that already works.
"""

from models import User, UserTablePreference

TABLE_PREFERENCE_SPECS: dict[str, dict[str, dict]] = {
    'staff_user': {
        'admin.users': {
            'columns': [
                {'name': 'username', 'visible': True, 'width': 260},
                {'name': 'preferred_name', 'visible': True, 'width': None},
                {'name': 'roles', 'visible': True, 'width': None},
                {'name': 'pronouns', 'visible': False, 'width': None},
            ],
            'density': 'compact',
        },
        'admin.schedule': {
            'columns': [
                {'name': 'players', 'visible': True, 'width': 320},
            ],
            'page_size': 25,
        },
    },
}


async def seed_table_preferences(users: dict[str, User]) -> None:
    """Give the staff fixture a customized layout on two boards. Idempotent."""
    for username, tables in TABLE_PREFERENCE_SPECS.items():
        user = users.get(username)
        if user is None:
            continue
        for table_key, config in tables.items():
            await UserTablePreference.get_or_create(
                user=user, table_key=table_key, defaults={'config': config},
            )
    print('  table preferences ok (global)')
