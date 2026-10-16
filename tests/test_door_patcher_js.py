"""Runs the patchers' JavaScript tests (tests/js/) under Node: door seeds and the generic ROM patcher."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which('node') is None, reason='needs Node')
def test_door_patcher_js():
    result = subprocess.run(
        ['node', '--no-warnings', '--test', 'tests/js/door_patcher.test.mjs', 'tests/js/rom_patcher.test.mjs'],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
