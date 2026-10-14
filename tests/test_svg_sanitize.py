"""``sanitise_svg`` keeps drawing content and drops everything that could act."""

import pytest

from application.utils.svg_sanitize import looks_like_svg, sanitise_svg

_NS = 'xmlns="http://www.w3.org/2000/svg"'


def _clean(body: str, attrs: str = 'viewBox="0 0 10 10"') -> str:
    return sanitise_svg(f'<svg {_NS} {attrs}>{body}</svg>'.encode()).decode()


def test_keeps_shapes_classes_and_styles():
    out = _clean('<defs><style>.a{fill:#ffce29}</style></defs><polygon class="a" points="0 0 5 5 0 5"/>')
    assert '<polygon class="a" points="0 0 5 5 0 5"' in out
    assert '.a{fill:#ffce29}' in out


@pytest.mark.parametrize('body', [
    '<script>alert(1)</script>',
    '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div></foreignObject>',
    '<image href="https://evil.example/x.png"/>',
    '<a href="javascript:alert(1)"><text>hi</text></a>',
    '<animate attributeName="href" to="javascript:alert(1)"/>',
    '<set attributeName="onclick" to="alert(1)"/>',
])
def test_drops_active_elements(body):
    out = _clean(body + '<rect width="1" height="1"/>')
    for word in ('script', 'foreignObject', 'image', 'javascript', 'animate', '<set', '<a ', 'evil'):
        assert word not in out


def test_drops_handlers_and_outside_references():
    out = _clean(
        '<rect id="r" width="1" height="1" onload="x()" fill="url(https://evil.example/#p)"/>'
        '<use href="https://evil.example/s.svg#r"/><use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#r"/>',
        'viewBox="0 0 10 10" onload="alert(1)"',
    )
    assert 'onload' not in out and 'evil' not in out
    assert '<use href="#r"' in out


@pytest.mark.parametrize('css', [
    '@import url(https://evil.example/x.css);',
    '.a{background:url(https://evil.example/x)}',
    '.a{fill:\\75rl(x)}',
])
def test_rejects_css_that_reaches_outside(css):
    with pytest.raises(ValueError):
        _clean(f'<style>{css}</style><rect width="1" height="1"/>')


def test_rejects_entities():
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><text>&b;</text></svg>'
    )
    with pytest.raises(ValueError):
        sanitise_svg(bomb)


def test_rejects_non_svg_and_empty_drawings():
    with pytest.raises(ValueError):
        sanitise_svg(b'<html><body/></html>')
    with pytest.raises(ValueError):
        sanitise_svg(b'not xml')
    with pytest.raises(ValueError):
        _clean('<title>nothing</title>')


def test_adds_viewbox_from_size():
    assert 'viewBox="0 0 40 20"' in _clean('<rect width="1" height="1"/>', 'width="40px" height="20"')
    with pytest.raises(ValueError):
        _clean('<rect width="1" height="1"/>', '')


def test_looks_like_svg():
    assert looks_like_svg(b'\xef\xbb\xbf<?xml version="1.0"?>\n<svg/>')
    assert not looks_like_svg(b'\x89PNG\r\n\x1a\n')
