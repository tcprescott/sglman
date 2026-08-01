"""Table Preference Repository - Data Access Layer

Handles database operations for per-user table layout preferences.

Deliberately **not** a :class:`TenantScopedRepository`: ``UserTablePreference``
has no tenant column (the same call as ``User``), so a scoped filter would raise
on a model that has nothing to scope. Every method keys off ``user_id`` alone.
"""

from typing import Optional

from models import UserTablePreference


class TablePreferenceRepository:
    """Data access for :class:`UserTablePreference`."""

    @staticmethod
    async def all_for_user(user_id: int) -> dict[str, dict]:
        """Every stored table config for one person, keyed by ``table_key``.

        **One query.** This is the only read a page build makes, however many
        tables the page hosts.
        """
        rows = await UserTablePreference.filter(user_id=user_id)
        return {r.table_key: (r.config or {}) for r in rows}

    @staticmethod
    async def get(user_id: int, table_key: str) -> Optional[UserTablePreference]:
        return await UserTablePreference.get_or_none(user_id=user_id, table_key=table_key)

    @staticmethod
    async def upsert(user_id: int, table_key: str, config: dict) -> UserTablePreference:
        row, _ = await UserTablePreference.update_or_create(
            user_id=user_id, table_key=table_key, defaults={'config': config})
        return row

    @staticmethod
    async def delete(user_id: int, table_key: str) -> bool:
        """Remove one table's config; returns whether a row existed."""
        deleted = await UserTablePreference.filter(
            user_id=user_id, table_key=table_key).delete()
        return bool(deleted)

    @staticmethod
    async def delete_all_for_user(user_id: int) -> int:
        """Remove every table config for one person; returns the row count."""
        return await UserTablePreference.filter(user_id=user_id).delete()
