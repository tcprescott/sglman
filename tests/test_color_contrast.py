"""WCAG contrast math + the guarantee that every shipped theme preset passes.

The preset-verification test is what makes "contrast-verified presets" a
guarantee rather than a claim: if a future edit to a preset (or to the contrast
thresholds) drops any preset field below AA, CI fails here.
"""

import pytest

from application.services.tenant_theme_service import (
    DEFAULT_THEME,
    THEME_PRESETS,
    TenantThemeService,
)
from application.utils.color_contrast import contrast_ratio, relative_luminance

_CHECKED_KEYS = {'primary', 'secondary', 'accent', 'header'}


# ---------------------------------------------------------------------------
# contrast math
# ---------------------------------------------------------------------------


class TestContrastMath:
    def test_black_on_white_is_max(self):
        assert round(contrast_ratio('#000000', '#ffffff'), 1) == 21.0

    def test_identical_colours_is_one(self):
        assert contrast_ratio('#123456', '#123456') == 1.0

    def test_is_symmetric(self):
        assert contrast_ratio('#9c6b12', '#ffffff') == contrast_ratio('#ffffff', '#9c6b12')

    def test_case_insensitive(self):
        assert contrast_ratio('#9C6B12', '#FFFFFF') == contrast_ratio('#9c6b12', '#ffffff')

    def test_luminance_endpoints(self):
        assert relative_luminance('#000000') == 0.0
        assert relative_luminance('#ffffff') == 1.0


# ---------------------------------------------------------------------------
# preset verification — the "verified" guarantee
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('name', list(THEME_PRESETS))
def test_every_preset_meets_aa_contrast(name):
    report = TenantThemeService.contrast_report(THEME_PRESETS[name])
    assert set(report) == _CHECKED_KEYS, f'{name} is missing a checked colour'
    failures = {k: r['ratio'] for k, r in report.items() if not r['ok']}
    assert not failures, f'{name} fails AA contrast: {failures}'


def test_default_theme_meets_aa_contrast():
    report = TenantThemeService.contrast_report(DEFAULT_THEME)
    assert all(r['ok'] for r in report.values())


def test_phoenix_preset_equals_default():
    assert THEME_PRESETS['Phoenix (default)'] == DEFAULT_THEME
