"""The SGL workbook importer's parsing: hyperlinks, durations, section boundary."""

import io
import zipfile
from datetime import datetime

from scripts.import_sgl_tournaments import (
    parse_minutes,
    parse_tournaments,
    read_sheet,
    seed_generator_for,
)

_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'

_HEADER = ['Tournament', 'Admin', 'Challonge', 'Qualifiers', 'Deadline', 'Trophies',
           'Schedule', 'Format', 'Ave Time', 'WCS Time', 'Seed Generation', 'Brackets', 'Rules']


def _xlsx(rows, links):
    """A minimal workbook with one 'Onsite' sheet of inline strings / numbers."""
    def cell(ref, value):
        if isinstance(value, (int, float)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'

    body = ''.join(
        f'<row r="{r}">' + ''.join(
            cell(f'{chr(65 + c)}{r}', v) for c, v in enumerate(row) if v is not None
        ) + '</row>'
        for r, row in enumerate(rows, start=1)
    )
    hyperlinks = ''.join(
        f'<hyperlink ref="{ref}" r:id="rId{i}"/>' for i, ref in enumerate(links, start=1)
    )
    sheet_rels = ''.join(
        f'<Relationship Id="rId{i}" Type="{_REL}/hyperlink" Target="{url}" TargetMode="External"/>'
        for i, url in enumerate(links.values(), start=1)
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('xl/workbook.xml',
                   f'<workbook xmlns="{_MAIN}" xmlns:r="{_REL}"><sheets>'
                   f'<sheet name="Onsite" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',
                   f'<Relationships xmlns="{_PKG}"><Relationship Id="rId1" '
                   f'Type="{_REL}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',
                   f'<worksheet xmlns="{_MAIN}" xmlns:r="{_REL}"><sheetData>{body}</sheetData>'
                   f'<hyperlinks>{hyperlinks}</hyperlinks></worksheet>')
        z.writestr('xl/worksheets/_rels/sheet1.xml.rels',
                   f'<Relationships xmlns="{_PKG}">{sheet_rels}</Relationships>')
    return buf.getvalue()


def _workbook():
    rows = [
        _HEADER,
        ['Ocarina of Time Randomizer', 'Dastar, KLO', 'sgl26ootr', 'Async\nPrior to Event',
         46310.5, '1st + 2nd', 'sgl26ootr', 'Single Elim Bo1\nFinal Bo3', '120-150 min',
         '195 min', 'https://ootrandomizer.com/generator', 'start.gg', 'Rules Doc'],
        ['Super Metroid Any%', 'Felix_tc', 'sgl26smany', 'No', 46316.749305555553,
         '1st + 2nd', None, 'Single Elim Bo1', '45 min', '75 min', 'N/A', None, 'Rules Doc'],
        ['Best of NES - Relay', 'lackattack'],
        ['Side Events', 'Admin', 'Challonge'],
        ['Poker Tournament', 'Rick'],
    ]
    links = {
        'C2': 'https://speedgaming.challonge.com/sgl26ootr',
        'L2': 'https://www.start.gg/tournament/ootr',
        'M2': 'https://docs.example/ootr',
        'K2': 'https://ootrandomizer.com/generator',
        'M3': 'https://docs.example/sm',
    }
    return _xlsx(rows, links)


def test_parses_rows_up_to_the_side_events_header():
    names = [t.name for t in parse_tournaments(read_sheet(_workbook(), 'Onsite'))]
    assert names == ['Ocarina of Time Randomizer', 'Super Metroid Any%', 'Best of NES - Relay']


def test_maps_hyperlinks_durations_and_deadline():
    ootr, sm, nes = parse_tournaments(read_sheet(_workbook(), 'Onsite'))

    assert ootr.challonge_url is None
    assert ootr.fields['bracket_url'] == 'https://www.start.gg/tournament/ootr'
    assert ootr.fields['rules_url'] == 'https://docs.example/ootr'
    assert ootr.fields['tournament_format'] == 'Single Elim Bo1; Final Bo3'
    assert ootr.fields['average_match_duration'] == 135
    assert ootr.fields['max_match_duration'] == 195
    assert ootr.fields['seed_generator'] == 'ootr'
    assert 'Qualifiers: Async; Prior to Event' in ootr.fields['description']
    assert ootr.deadline == datetime(2026, 10, 15, 12, 0)

    assert sm.deadline == datetime(2026, 10, 21, 17, 59)
    assert sm.fields['bracket_url'] == 'https://challonge.com/sgl26smany'
    assert 'seed_generator' not in sm.fields
    assert 'Qualifiers' not in sm.fields['description']
    assert 'Seed generation' not in sm.fields['description']

    assert nes.challonge_url is None
    assert set(nes.fields) == {'description'}


def test_parse_minutes():
    assert parse_minutes('90 min') == 90
    assert parse_minutes('120-150 min') == 135
    assert parse_minutes('') is None


def test_seed_generator_maps_alttpr_variants():
    assert seed_generator_for('A Link to the Past Randomizer Hybrid Major Glitches') == 'alttpr'
    assert seed_generator_for('A Link to the Past Any% No Major Glitches') is None
    assert seed_generator_for('A Link to the Past Randomizer') == 'alttpr'
    assert seed_generator_for('Super Metroid: DASH') == 'smdash'
