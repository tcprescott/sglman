"""Mechanical half of docs/style-guide.md.

The 2026-10 style pass (Studio tokens, one chip, three dialog sizes) and the
accessibility audit that followed fixed whole classes of drift at once: nine
dialog widths, colours hand-picked per page, dark-mode text that read the
light-mode ink. Each check here pins one of those fixes so a later page can't
quietly reintroduce it. The browser half (rendered contrast and axe, in light
and dark) is scripts/ui_a11y_scan.js in CI.

A line that genuinely needs an exception says so in place with
``# style-guide: exempt — <reason>`` (Python) or
``/* style-guide: exempt — <reason> */`` (CSS).
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
STYLES = ROOT / 'static' / 'css' / 'styles.css'
CSS_FILES = [STYLES, ROOT / 'static' / 'css' / 'brackets.css']
EXEMPT = 'style-guide: exempt'

_COLOUR_LITERAL = re.compile(r'#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(')
_WIDTH_CLASS = re.compile(r'(?:^|\s)(?:w-\S+|min-w-\S+|max-w-\S+|full-width)(?:\s|$)')
_TITLE_CLASS = re.compile(r'(?:^|\s)text-h[1-6](?:\s|$)')


def _python_sources():
    for path in sorted([*ROOT.joinpath('pages').rglob('*.py'), *ROOT.joinpath('theme').rglob('*.py')]):
        source = path.read_text()
        yield path.relative_to(ROOT), source, ast.parse(source), source.splitlines()


def _exempt(lines: list[str], lineno: int) -> bool:
    return EXEMPT in lines[lineno - 1]


def _ui_call(node: ast.AST) -> str | None:
    """`ui.card().classes(...)` → 'card'."""
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name) and node.func.value.id == 'ui':
            return node.func.attr
        node = node.func.value
    return None


def _chained(node: ast.AST, method: str) -> list[ast.Call]:
    calls = []
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == method:
            calls.append(node)
        node = node.func.value
    return calls


def _dialog_cards():
    for rel, _source, tree, lines in _python_sources():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.With, ast.AsyncWith)):
                continue
            exprs = [item.context_expr for item in node.items]
            if 'dialog' not in [_ui_call(e) for e in exprs]:
                continue
            cards = [e for e in exprs if _ui_call(e) == 'card']
            if not cards and node.body and isinstance(node.body[0], (ast.With, ast.AsyncWith)):
                cards = [i.context_expr for i in node.body[0].items if _ui_call(i.context_expr) == 'card']
            for card in cards:
                yield f'{rel}:{card.lineno}', card, lines


def test_dialog_cards_use_the_three_standard_sizes():
    """A dialog card is `dialog-card` (+ `--sm`/`--lg`), never its own width.

    Wave 2 of the style pass replaced 23 one-off dialog widths with three
    sizes; `w-96`, `w-full` and inline `max-width` were how they crept in.
    """
    bad = []
    for where, card, lines in _dialog_cards():
        if _exempt(lines, card.lineno):
            continue
        if _chained(card, 'style'):
            bad.append(f'{where}: sized with .style(); use dialog-card--sm|md|lg')
            continue
        classes = _chained(card, 'classes')
        if not classes:
            bad.append(f'{where}: no dialog-card class')
            continue
        arg = classes[-1].args[0] if classes[-1].args else None
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            continue  # a parameter, e.g. form_dialog(card_classes=...)
        if 'dialog-card' not in arg.value.split():
            bad.append(f'{where}: classes {arg.value!r} lack dialog-card')
        elif _WIDTH_CLASS.search(arg.value):
            bad.append(f'{where}: width class in {arg.value!r}; use dialog-card--sm|md|lg')
    assert not bad, 'Dialog cards off the standard sizes:\n  ' + '\n  '.join(bad)


def test_inline_styles_carry_no_colour_literals():
    """Colour comes from tokens, not from a hex in `.style()` or a slot's `style=`."""
    bad = []
    for rel, source, tree, lines in _python_sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'style':
                segment = ast.get_source_segment(source, node) or ''
                if _COLOUR_LITERAL.search(segment) and not _exempt(lines, node.lineno):
                    bad.append(f'{rel}:{node.lineno}')
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and 'style="' in node.value:
                for match in re.finditer(r'style="([^"]*)"', node.value):
                    if _COLOUR_LITERAL.search(match.group(1)) and not _exempt(lines, node.lineno):
                        bad.append(f'{rel}:{node.lineno} (template)')
    assert not bad, (
        'Inline colour literals (use a token such as var(--fg-muted) or a .st-*/.wiz-chip--* class):\n  '
        + '\n  '.join(bad)
    )


def test_titles_come_from_page_header_not_typography_classes():
    """`text-h1`…`text-h6` labels were the third page-top style, and 35 `text-h6`
    section headings sat beside `section-title` in a different size and weight."""
    bad = []
    for rel, _source, tree, lines in _python_sources():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'classes'):
                continue
            for arg in node.args:
                values = [arg.value] if isinstance(arg, ast.Constant) else [
                    v.value for v in getattr(arg, 'values', []) if isinstance(v, ast.Constant)
                ]
                if any(isinstance(v, str) and _TITLE_CLASS.search(v) for v in values) and not _exempt(lines, node.lineno):
                    bad.append(f'{rel}:{node.lineno}')
    assert not bad, 'Heading-size classes (use page_header / section_panel / dialog_header):\n  ' + '\n  '.join(bad)




def test_dialogs_use_the_shared_header():
    """A hand-built `ui.dialog()` + `ui.card()` skipped dialog_header, so it had no
    accessible name, no close button and no phone sheet. Use form_dialog."""
    bad = []
    for rel, _source, tree, lines in _python_sources():
        if rel.as_posix() == 'theme/dialog/_helpers.py':
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.With, ast.AsyncWith)):
                continue
            if 'dialog' not in [_ui_call(i.context_expr) for i in node.items]:
                continue
            calls = {
                n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, 'attr', '')
                for stmt in node.body for n in ast.walk(stmt) if isinstance(n, ast.Call)
            }
            if 'dialog_header' not in calls and not _exempt(lines, node.lineno):
                bad.append(f'{rel}:{node.lineno}')
    assert not bad, 'Dialogs without dialog_header (use form_dialog):\n  ' + '\n  '.join(bad)

def _is_help_icon(stmt: ast.stmt) -> bool:
    call = stmt.value.value if (
        isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await)
    ) else None
    return isinstance(call, ast.Call) and getattr(call.func, 'id', '') == 'help_icon'


def test_one_help_button_per_heading():
    """Help lives in one "?" per heading or dialog title, listing every topic.

    Two calls side by side were the scattered icons this replaced; pass the
    topics to one call. In a dialog the button goes in the title bar
    (``dialog_header(..., help=)`` / ``form_dialog(..., help=)``), never in
    the body beside a control.
    """
    bad = []
    for rel, _source, tree, lines in _python_sources():
        if rel.as_posix().startswith('theme/help/'):
            continue
        for node in ast.walk(tree):
            for field in ('body', 'orelse'):
                stmts = getattr(node, field, None)
                if isinstance(stmts, list) and sum(_is_help_icon(st) for st in stmts) > 1:
                    first = next(st for st in stmts if _is_help_icon(st))
                    if not _exempt(lines, first.lineno):
                        bad.append(f'{rel}:{first.lineno}: two help_icon calls; pass both topics to one')
            if isinstance(node, (ast.With, ast.AsyncWith)) and any(
                _ui_call(i.context_expr) == 'dialog'
                or getattr(getattr(i.context_expr, 'func', None), 'id', '') == 'form_dialog'
                for i in node.items
            ):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.stmt) and _is_help_icon(inner) and not _exempt(lines, inner.lineno):
                        bad.append(f'{rel}:{inner.lineno}: help_icon in a dialog body; use dialog_header(help=)')
    assert not bad, 'Help buttons out of place:\n  ' + '\n  '.join(bad)


def test_toggles_use_the_segmented_control():
    """A bare `ui.toggle` is Quasar's gold button row; the app's switch is `.wiz-segmented`."""
    bad = []
    for rel, source, tree, lines in _python_sources():
        chains = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _ui_call(n) == 'toggle']
        inner = {id(n.func.value) for n in chains if isinstance(n.func, ast.Attribute)}
        for chain in chains:
            if id(chain) in inner:
                continue
            classes = ' '.join(ast.get_source_segment(source, c) or '' for c in _chained(chain, 'classes'))
            if 'wiz-segmented' not in classes and not _exempt(lines, chain.lineno):
                bad.append(f'{rel}:{chain.lineno}')
    assert not bad, 'Toggles without .wiz-segmented:\n  ' + '\n  '.join(bad)


def test_clipboard_writes_go_through_the_shared_helper():
    """Every Copy button calls `theme.clipboard.copy_to_clipboard`, so they all toast alike."""
    bad = []
    for rel, source, tree, lines in _python_sources():
        if rel.as_posix() == 'theme/clipboard.py':
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'run_javascript'
                    and 'clipboard' in (ast.get_source_segment(source, node) or '')
                    and not _exempt(lines, node.lineno)):
                bad.append(f'{rel}:{node.lineno}')
    assert not bad, 'Inline clipboard writes (use copy_to_clipboard):\n  ' + '\n  '.join(bad)

_DISMISS_LABELS = {'Cancel', 'Close', 'Back', 'Not now', 'Keep editing'}


def _base_name(call: ast.AST) -> str | None:
    """`dialog_actions().classes(...)` → 'dialog_actions'."""
    while isinstance(call, ast.Call):
        if isinstance(call.func, ast.Name):
            return call.func.id
        call = call.func.value if isinstance(call.func, ast.Attribute) else None
    return None


def _ui_buttons(stmts: list[ast.stmt]) -> list[ast.Call]:
    """Each `ui.button(...)` chain (props and classes included), in source order."""
    chains = [n for st in stmts for n in ast.walk(st) if isinstance(n, ast.Call) and _ui_call(n) == 'button']
    inner = {id(n.func.value) for n in chains if isinstance(n.func, ast.Attribute)}
    return sorted((c for c in chains if id(c) not in inner), key=lambda c: (c.lineno, c.col_offset))


def _button_label(chain: ast.Call) -> str | None:
    while isinstance(chain.func, ast.Attribute) and isinstance(chain.func.value, ast.Call):
        chain = chain.func.value
    first = chain.args[0] if chain.args else None
    return first.value if isinstance(first, ast.Constant) else None


def test_dialog_footer_puts_the_primary_action_last():
    """Negative on the left, positive on the right: Cancel sits just left of the
    primary button, never after it. A destructive action (Delete) goes at the far
    left, before the dismiss button."""
    bad = []
    for rel, source, tree, lines in _python_sources():
        for node in ast.walk(tree):
            if not (isinstance(node, (ast.With, ast.AsyncWith))
                    and any(_base_name(i.context_expr) == 'dialog_actions' for i in node.items)):
                continue
            seen_primary = False
            for button in _ui_buttons(node.body):
                label = _button_label(button)
                if seen_primary and label in _DISMISS_LABELS and not _exempt(lines, button.lineno):
                    bad.append(f'{rel}:{button.lineno}: {label!r} after the primary button')
                text = ast.get_source_segment(source, button) or ''
                if re.search(r"color=primary|color='primary'", text):
                    seen_primary = True
    assert not bad, 'Dialog footers out of order:\n  ' + '\n  '.join(bad)


def test_overflow_menus_use_the_vertical_dots():
    """⋮ (`more_vert`) is the one overflow icon on rows, cards and sheets; a ⋯ beside it reads as a different control."""
    bad = [
        f'{rel}:{i}'
        for rel, source, _tree, lines in _python_sources()
        for i, line in enumerate(lines, 1)
        if 'more_horiz' in line and EXEMPT not in line
    ]
    assert not bad, 'more_horiz overflow buttons (use more_vert):\n  ' + '\n  '.join(bad)


def _menu_item_kind(stmt: ast.stmt, source: str) -> str | None:
    """'negative', 'item' or None for one statement directly inside a `ui.menu()`."""
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
    elif isinstance(stmt, (ast.With, ast.AsyncWith)) and isinstance(stmt.items[0].context_expr, ast.Call):
        call = stmt.items[0].context_expr
    else:
        return None
    name = _ui_call(call) or _base_name(call)
    if name not in ('menu_item', 'menu_action'):
        return None
    text = ast.get_source_segment(source, call) or ''
    negative = 'text-negative' in text or 'color=negative' in text or any(
        k.arg == 'negative' and isinstance(k.value, ast.Constant) and k.value.value is True
        for k in call.keywords
    )
    return 'negative' if negative else 'item'


def test_destructive_menu_items_come_last():
    """In an Actions or ⋮ menu the red item (Delete, Reset) is the last one, set
    apart, so the item people reach for most isn't next to it."""
    bad = []
    for rel, source, tree, lines in _python_sources():
        for node in ast.walk(tree):
            if not (isinstance(node, (ast.With, ast.AsyncWith))
                    and any(_ui_call(i.context_expr) == 'menu' for i in node.items)):
                continue
            kinds = [(st, _menu_item_kind(st, source)) for st in node.body]
            kinds = [(st, k) for st, k in kinds if k]
            seen_negative = None
            for st, kind in kinds:
                if kind == 'negative':
                    seen_negative = st
                elif seen_negative is not None and not _exempt(lines, seen_negative.lineno):
                    bad.append(f'{rel}:{seen_negative.lineno}: destructive item before {st.lineno}')
                    break
    assert not bad, 'Destructive menu items not last:\n  ' + '\n  '.join(bad)


def test_side_menu_is_224px():
    """The drawer's longest label needs about 175px; Quasar's 300px default left a
    wide empty strip beside the nav on desktop."""
    base = (ROOT / 'theme' / 'base.py').read_text()
    assert re.search(r"bordered width=224\b", base), 'The side menu drawer should be width=224'


# --- styles.css ---------------------------------------------------------------

def _strip_comments(css: str) -> str:
    return re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group(0).count('\n'), css, flags=re.S)


def test_css_colour_literals_live_in_tokens():
    """A hex colour in a rule (not a `--token:` definition) skips dark mode and the tenant palette.

    #fff/#000 are allowed for text on a fill; anything else either becomes a
    token or carries an exempt comment saying why it can't.
    """
    bad = []
    for path in CSS_FILES:
        raw = path.read_text().splitlines()
        for lineno, line in enumerate(_strip_comments(path.read_text()).splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith('--') or EXEMPT in raw[lineno - 1]:
                continue
            for hex_value in re.findall(r'#[0-9a-fA-F]{3,8}\b', stripped):
                if hex_value.lower() not in {'#fff', '#ffffff', '#000', '#000000'}:
                    bad.append(f'{path.relative_to(ROOT)}:{lineno}: {stripped}')
    assert not bad, 'Raw colours outside token definitions:\n  ' + '\n  '.join(bad)


def _token_block(selector_pattern: str) -> dict[str, str]:
    css = _strip_comments(STYLES.read_text())
    tokens: dict[str, str] = {}
    for match in re.finditer(selector_pattern + r'\s*\{([^}]*)\}', css):
        for name, value in re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', match.group(1)):
            tokens.setdefault(name, value.strip())
    return tokens


ROOT_TOKENS = _token_block(r'(?m)^:root')
DARK_TOKENS = _token_block(r'(?m)^\.body--dark,\s*\n\.q-dark')


def test_dark_block_restates_every_alias_of_a_dark_token():
    """`--x: var(--fg)` on :root resolves to the *light* ink, once, at :root.

    Custom properties compute where they are declared, so an alias that is not
    restated under `.body--dark` keeps the light value in dark mode. That left
    settings card titles and the On Air stage names near-black on dark.
    """
    def refs(value: str) -> set[str]:
        return set(re.findall(r'var\((--[\w-]+)', value))

    dark_aware = set(DARK_TOKENS)
    changed = True
    while changed:
        changed = False
        for name, value in ROOT_TOKENS.items():
            if name not in dark_aware and refs(value) & dark_aware:
                dark_aware.add(name)
                changed = True
    stale = sorted(n for n in dark_aware - set(DARK_TOKENS) if n in ROOT_TOKENS)
    assert not stale, (
        'These :root tokens derive from a token that changes in dark mode but are not '
        'restated in the .body--dark/.q-dark block: ' + ', '.join(stale)
    )


def _resolve(name: str, dark: bool, depth: int = 0) -> tuple[float, float, float]:
    assert depth < 20, f'{name}: var() cycle'
    value = (DARK_TOKENS.get(name) if dark else None) or ROOT_TOKENS[name]
    return _colour(value, dark, depth)


def _colour(value: str, dark: bool, depth: int = 0) -> tuple[float, float, float]:
    value = value.strip()
    if value.startswith('var('):
        return _resolve(re.match(r'var\((--[\w-]+)', value).group(1), dark, depth + 1)
    if value.startswith('#'):
        h = value[1:]
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    mix = re.fullmatch(r'color-mix\(in srgb,\s*(.+?)\s+(\d+)%,\s*(.+)\)', value)
    if mix:
        a, pct, b = _colour(mix.group(1), dark, depth), int(mix.group(2)) / 100, _colour(mix.group(3), dark, depth)
        return tuple(x * pct + y * (1 - pct) for x, y in zip(a, b, strict=True))  # type: ignore[return-value]
    raise AssertionError(f'cannot resolve colour {value!r}')


def _contrast(a, b) -> float:
    def lum(c):
        def f(v):
            v /= 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


TEXT_TOKENS = [
    '--fg', '--fg-secondary', '--fg-muted', '--wiz-link',
    '--status-ok', '--status-pending', '--status-live', '--status-neutral', '--status-cancelled', '--status-info',
]
SURFACES = ['--surface', '--page-bg', '--surface-alt']


@pytest.mark.parametrize('dark', [False, True], ids=['light', 'dark'])
@pytest.mark.parametrize('text', TEXT_TOKENS)
def test_text_tokens_meet_aa_on_every_surface(text, dark):
    """Every token meant for text clears 4.5:1 on every surface, in both modes."""
    fg = _resolve(text, dark)
    for surface in SURFACES:
        ratio = _contrast(fg, _resolve(surface, dark))
        assert ratio >= 4.5, f'{text} on {surface} ({"dark" if dark else "light"}) is {ratio:.2f}:1'


def test_white_label_meets_aa_on_the_default_accent_fill():
    ratio = _contrast((255, 255, 255), _resolve('--wiz-gold-deep', False))
    assert ratio >= 4.5, f'white on the default accent is {ratio:.2f}:1'


def test_theme_editor_contrast_checks_match_the_stylesheet():
    """The Appearance editor's contrast warnings model these tokens and rules;
    if styles.css moves a surface or a brand-text mix, the warnings must follow."""
    from application.services import tenant_theme_service as theme

    def hexed(rgb) -> str:
        return '#' + ''.join(f'{round(c):02x}' for c in rgb)

    assert theme._LIGHT_SURFACES == tuple(hexed(_resolve(s, False)) for s in SURFACES)
    assert theme._DARK_SURFACES == tuple(hexed(_resolve(s, True)) for s in SURFACES)
    assert ROOT_TOKENS['--wiz-link'].strip() == 'color-mix(in srgb, var(--accent) 85%, #000)'
    assert 'body:not(.body--dark) .text-primary { color: color-mix(in srgb, var(--q-primary) 85%, #000)' in STYLES.read_text()
    assert '.body--dark .text-secondary { color: color-mix(in srgb, var(--wiz-ember) 70%, #fff)' in STYLES.read_text()
    assert DARK_TOKENS['--wiz-link'].strip() == 'var(--wiz-gold)'


def test_collapsible_filter_cards_have_a_toggle():
    """Below 1024px ``.match-filters-card`` is hidden until a Filters toggle opens it.

    A page that uses the card without a toggle strands phone users on its
    default filter (Triforce Texts did, 2026-10).
    """
    offenders = [
        str(rel)
        for rel, source, _tree, _lines in _python_sources()
        if "'match-filters-card" in source
        and 'wiz-filter-toggle' not in source
        and EXEMPT not in source
    ]
    assert not offenders, (
        'These use .match-filters-card, which CSS hides below 1024px, but render no '
        f'.wiz-filter-toggle / .wiz-filter-toggle--inline button to open it: {offenders}'
    )
