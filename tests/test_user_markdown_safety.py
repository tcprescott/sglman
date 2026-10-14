"""Markdown a player or volunteer writes, and the Discord copy built from member input.

Staff-authored fields render through the full help model; match comments and
community event descriptions go through ``parse_user_blocks`` instead, because
someone else reads them.
"""

import pytest

from application.content import parse_blocks, parse_user_blocks
from application.services.web_push_service import _MARKDOWN_TOKENS
from application.utils.discord_messages_community_events import (
    literal,
    reminder_dm,
    submitted_to_staff_dm,
)


def _spans(blocks):
    return [span for block in blocks for span in (*block.spans, *[s for item in block.items for s in item])]


@pytest.mark.parametrize('href', [
    '//evil.example/login',
    '/\\evil.example/login',
    '/ok\\..\\x',
    'https://evil.example\\@good',
])
@pytest.mark.parametrize('parse', [parse_blocks, parse_user_blocks])
def test_off_site_lookalike_paths_are_not_links(parse, href):
    spans = _spans(parse(f'[Re-login]({href})'))
    assert all(span.kind != 'link' for span in spans)


@pytest.mark.parametrize('parse', [parse_blocks, parse_user_blocks])
def test_ordinary_links_still_link(parse):
    spans = _spans(parse('[home](/t/sgl/home) and [site](https://example.com/x)'))
    assert [span.href for span in spans if span.kind == 'link'] == ['/t/sgl/home', 'https://example.com/x']


def test_user_blocks_are_only_paragraphs_and_lists():
    text = '\n'.join([
        '## Heading',
        '> a quote',
        '{chip:ok:Paid} {state:Confirmed}',
        '',
        '![Login](/static/help/community-events/listing-phone.webp)',
        '',
        '| a | b |',
        '|---|---|',
        '| 1 | 2 |',
        '',
        '- one',
        '1. two',
    ])
    blocks = parse_user_blocks(text)
    assert {block.kind for block in blocks} <= {'para', 'bullets', 'numbers'}
    assert all(not block.anchor for block in blocks)
    assert {span.kind for span in _spans(blocks)} <= {'text', 'strong', 'em', 'code', 'link'}


def test_user_heading_reads_as_bold_text():
    [block] = parse_user_blocks('## Bring a controller')
    assert block.kind == 'para'
    assert [(span.kind, span.text) for span in block.spans] == [('strong', 'Bring a controller')]


def test_member_text_cannot_form_a_discord_masked_link():
    message = submitted_to_staff_dm('SG', '[Staff](https://evil)', '[Approve here](https://evil)')
    assert '[Approve here](' not in message
    assert '[Staff](' not in message
    assert '[x](' not in reminder_dm('Meetup', 'soon', '[x](https://evil)')
    assert literal(None) == ''


def test_web_push_drops_the_bracket_escapes():
    message = submitted_to_staff_dm('SG', 'Ana', '[Draft] Meetup')
    assert _MARKDOWN_TOKENS.sub('', message).startswith('Ana submitted [Draft] Meetup')
