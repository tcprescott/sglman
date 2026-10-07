"""Tests for the pure log-level helpers behind the /platform Logging section."""

import logging

import pytest

from application.utils import log_levels


def test_level_number_accepts_every_offered_level():
    for name in log_levels.LEVELS:
        assert isinstance(log_levels.level_number(name.lower()), int)
    assert log_levels.level_number('TRACE') == log_levels.TRACE < logging.DEBUG


def test_level_number_rejects_others():
    with pytest.raises(ValueError):
        log_levels.level_number('VERBOSE')


@pytest.mark.parametrize('raw,expected', [
    ('', ''), ('root', ''), (' application.services ', 'application.services'),
    ('uvicorn.access', 'uvicorn.access'),
])
def test_normalize_logger_name(raw, expected):
    assert log_levels.normalize_logger_name(raw) == expected


@pytest.mark.parametrize('raw', ['has space', '.leading', 'semi;colon'])
def test_normalize_rejects_non_module_names(raw):
    with pytest.raises(ValueError):
        log_levels.normalize_logger_name(raw)


def test_register_trace_level_names_it():
    log_levels.register_trace_level()
    assert logging.getLevelName(log_levels.TRACE) == 'TRACE'
    assert log_levels.level_label(log_levels.TRACE) == 'TRACE'


def test_default_root_level_reads_env(monkeypatch):
    monkeypatch.setenv('LOG_LEVEL', 'warning')
    assert log_levels.default_root_level() == logging.WARNING
    monkeypatch.setenv('LOG_LEVEL', 'nonsense')
    assert log_levels.default_root_level() == logging.INFO


def test_known_loggers_are_unique_and_valid():
    names = [k.name for k in log_levels.KNOWN_LOGGERS]
    assert len(names) == len(set(names))
    for name in names:
        assert log_levels.normalize_logger_name(name) == name
