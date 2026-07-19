"""WCAG relative-luminance and contrast-ratio math (pure, dependency-free).

Used by the tenant theme editor to warn when a brand colour is hard to read
against the surface it paints on, and by the preset-verification test. Inputs are
6-digit ``#rrggbb`` hex strings (the theme service validates before calling).

Formulae are the W3C definitions:
- relative luminance — https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
- contrast ratio     — https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio
"""


def _linearize(channel_8bit: int) -> float:
    """sRGB 8-bit channel → linear-light component (WCAG)."""
    c = channel_8bit / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def relative_luminance(hex_color: str) -> float:
    """Relative luminance of a colour in [0.0 (black), 1.0 (white)]."""
    r, g, b = _rgb(hex_color)
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two colours, in [1.0, 21.0]. Symmetric."""
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = (la, lb) if la >= lb else (lb, la)
    return (lighter + 0.05) / (darker + 0.05)
