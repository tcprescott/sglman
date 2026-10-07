"""Tests for LogLevelService — runtime logger levels set on /platform.

What matters: only SUPER_ADMIN may change a level, a change lands on the live
logging tree at once, it is stored so a restart reapplies it, and clearing puts
the logger back to inheriting its parent.
"""

import logging

import pytest

from application.services import LogLevelService
from application.services.audit_service import AuditActions
from application.utils.log_levels import TRACE, default_root_level
from models import AuditLog, LogLevelOverride, Role, User, UserRole

_NAME = 'wizzrobe.test.log_levels'


@pytest.fixture
async def super_admin(db):
    su = await User.create(discord_id=2000, username='root')
    await UserRole.create(user=su, role=Role.SUPER_ADMIN, tenant=None)
    return su


@pytest.fixture
async def plain_user(db):
    return await User.create(discord_id=2001, username='nobody')


@pytest.fixture(autouse=True)
def _restore_levels():
    target = logging.getLogger(_NAME)
    root = logging.getLogger()
    saved = (target.level, root.level)
    yield
    target.setLevel(saved[0])
    root.setLevel(saved[1])


async def test_set_level_requires_super_admin(plain_user):
    with pytest.raises(PermissionError):
        await LogLevelService().set_level(plain_user, _NAME, 'DEBUG')


async def test_set_level_applies_stores_and_audits(super_admin):
    await LogLevelService().set_level(super_admin, _NAME, 'debug')

    assert logging.getLogger(_NAME).level == logging.DEBUG
    row = await LogLevelOverride.get(logger_name=_NAME)
    assert row.level == 'DEBUG'
    assert row.updated_by_id == super_admin.id
    assert await AuditLog.filter(action=AuditActions.LOG_LEVEL_SET).count() == 1


async def test_trace_level_is_below_debug(super_admin):
    await LogLevelService().set_level(super_admin, _NAME, 'TRACE')
    assert logging.getLogger(_NAME).level == TRACE


async def test_rejects_unknown_level_and_bad_name(super_admin):
    service = LogLevelService()
    with pytest.raises(ValueError):
        await service.set_level(super_admin, _NAME, 'LOUD')
    with pytest.raises(ValueError):
        await service.set_level(super_admin, 'not a logger', 'DEBUG')
    assert await LogLevelOverride.all().count() == 0


async def test_clear_restores_inheritance(super_admin):
    service = LogLevelService()
    await service.set_level(super_admin, _NAME, 'ERROR')
    await service.clear(super_admin, _NAME)

    assert logging.getLogger(_NAME).level == logging.NOTSET
    assert await LogLevelOverride.filter(logger_name=_NAME).count() == 0
    assert await AuditLog.filter(action=AuditActions.LOG_LEVEL_CLEARED).count() == 1


async def test_clearing_root_returns_to_the_boot_level(super_admin):
    service = LogLevelService()
    await service.set_level(super_admin, 'root', 'CRITICAL')
    assert logging.getLogger().level == logging.CRITICAL
    await service.clear(super_admin, '')
    assert logging.getLogger().level == default_root_level()


async def test_apply_persisted_reapplies_and_skips_bad_rows(db):
    await LogLevelOverride.create(logger_name=_NAME, level='WARNING')
    await LogLevelOverride.create(logger_name='wizzrobe.test.renamed', level='CHATTY')
    logging.getLogger(_NAME).setLevel(logging.NOTSET)

    applied = await LogLevelService().apply_persisted()

    assert applied == 1
    assert logging.getLogger(_NAME).level == logging.WARNING


async def test_list_rows_shows_known_and_custom_loggers(super_admin):
    service = LogLevelService()
    await service.set_level(super_admin, _NAME, 'DEBUG')

    rows = {r.name: r for r in await service.list_rows(super_admin)}

    assert '' in rows and rows[''].override is None
    custom = rows[_NAME]
    assert custom.override == 'DEBUG'
    assert custom.effective == 'DEBUG'
    assert custom.updated_by == 'root'
