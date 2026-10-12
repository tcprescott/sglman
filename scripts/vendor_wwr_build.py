"""Vendor one Wind Waker Randomizer build's permalink tables into Wizzrobe.

Run against a wwrando checkout at the exact commit the build was released from:

    git -C wwrando checkout d30d27c
    python scripts/vendor_wwr_build.py path/to/wwrando dev_tanjo3.1.10.7.3_d30d27c

``<version>`` is the string the build writes at the front of its permalinks
(``version.txt`` plus the ``_<commit>`` suffix the release CI appends), so it
must match what ``_seedgen_wwr.decode`` reads out of a permalink byte for byte.

Writes ``application/services/_wwr_data/<version>/``:

* ``permalink_spec.json``, the option order and bit widths the build packs a
  permalink with, read from its ``Options`` dataclass, ``wwr_ui/inventory.py``,
  ``logic/item_locations.txt`` and ``logic/tricks.py``;
* ``adjectives.txt``, ``nouns.txt``, ``names.txt``, the seed-name word lists;
* ``LICENSE``, wwrando's MIT notice.

Only builds whose encoder packs by option type (the post-1.10.0 ``Options``
dataclass) are supported. Imports the checkout's ``options`` package, which on
Python 3.13 needs the two shims below.
"""

from __future__ import annotations

import dataclasses
import json
import re
import reprlib
import shutil
import subprocess
import sys
import typing
from enum import StrEnum
from pathlib import Path

import yaml

OUT_ROOT = Path(__file__).resolve().parent.parent / 'application' / 'services' / '_wwr_data'


def build_spec(checkout: Path, version: str) -> dict:
    # wwrando imports a private helper that Python 3.13 removed.
    dataclasses._recursive_repr = reprlib.recursive_repr()  # type: ignore[attr-defined]
    sys.path.insert(0, str(checkout))
    from options.wwrando_options import Options  # type: ignore[import-not-found]
    from wwr_ui.inventory import PROGRESSIVE_ITEMS, REGULAR_ITEMS  # type: ignore[import-not-found]

    encoder = (checkout / 'randomizer.py').read_text()
    progressive_bits = int(re.search(
        r'for item_name in unique_progressive_items:\s*\n\s*bitswriter\.write\(value\.count\(item_name\), (\d+)\)',
        encoder,
    ).group(1))
    compressed = 'zlib.compress(permalink)' in encoder

    with open(checkout / 'logic' / 'item_locations.txt') as f:
        locations = list(yaml.safe_load(f))
    tricks = sorted(re.findall(r'Trick\(\s*name="([^"]+)"', (checkout / 'logic' / 'tricks.py').read_text()))

    fields: list[dict] = []
    for option in Options.all():
        if not option.permalink:
            continue
        kind = typing.get_origin(option.type) or option.type
        if kind is bool:
            fields.append({'name': option.name, 'kind': 'bool'})
        elif isinstance(kind, type) and issubclass(kind, StrEnum):
            fields.append({'name': option.name, 'kind': 'enum', 'values': [v.value for v in option.type]})
        elif kind is int:
            fields.append({'name': option.name, 'kind': 'int', 'min': option.minimum, 'max': option.maximum})
        elif option.name == 'starting_gear':
            fields.append({
                'name': option.name, 'kind': 'starting_gear',
                'regular': list(REGULAR_ITEMS),
                'progressive': sorted(set(PROGRESSIVE_ITEMS)),
                'progressive_bits': progressive_bits,
            })
        elif option.name == 'randomized_gear':
            continue
        elif option.name == 'excluded_locations':
            fields.append({'name': option.name, 'kind': 'flags', 'values': locations})
        elif option.name == 'enabled_tricks':
            fields.append({'name': option.name, 'kind': 'flags', 'values': tricks})
        else:
            raise SystemExit(f'Unsupported permalink option {option.name!r} ({option.type})')

    commit = subprocess.run(
        ['git', '-C', str(checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True,
    ).stdout.strip()
    return {
        'version': version,
        'source_commit': commit,
        'compressed': compressed,
        'fields': fields,
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    checkout, version = Path(sys.argv[1]).resolve(), sys.argv[2]
    out = OUT_ROOT / version
    out.mkdir(parents=True, exist_ok=True)
    spec = build_spec(checkout, version)
    (out / 'permalink_spec.json').write_text(json.dumps(spec, indent=1) + '\n')
    for name in ('adjectives.txt', 'nouns.txt', 'names.txt'):
        shutil.copyfile(checkout / 'seedgen' / name, out / name)
    shutil.copyfile(checkout / 'LICENSE.txt', out / 'LICENSE')
    print(f'Wrote {out} ({len(spec["fields"])} permalink fields, source {spec["source_commit"][:7]})')


if __name__ == '__main__':
    main()
