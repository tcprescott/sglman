"""The server and usage.js must normalise paths the same way, or tab rows and
click rows for one screen land under different paths."""

import re
from pathlib import Path

from theme.usage_telemetry import normalize_path


def test_strips_tenant_prefix_and_ids():
    assert normalize_path('/t/sgl26/admin') == '/admin'
    assert normalize_path('/t/sgl26/checkin/42') == '/checkin/{id}'
    assert normalize_path('/t/sgl26') == '/'
    assert normalize_path('/brackets/7/view') == '/brackets/{id}/view'
    assert normalize_path('/admin/schedule') == '/admin/schedule'


def test_usage_js_uses_the_same_rules():
    js = Path(__file__).resolve().parents[2].joinpath('static/js/usage.js').read_text()
    assert "replace(/^\\/t\\/[^/]+/, '')" in js
    assert re.search(r"replace\(/\\/\\d\+\(\?=\\/\|\$\)/g, '/\{id\}'\)", js)
