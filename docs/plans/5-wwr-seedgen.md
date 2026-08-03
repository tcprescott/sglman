# Wind Waker seed generation (`wwr`) — research notes

**Not a plan.** `wwr` is a registered stub in
[`seedgen_service.py`](../../application/services/seedgen_service.py) — selectable on a
tournament, present in every UI/API surface, and raising `ValueError` when
rolled. Nothing automated it at SGL25. This file records what the wwrando repo
answers, so the decision can be made before the September 2026 freeze.

Majora's Mask is a separate problem with a separate answer:
[4-mmr-seedgen.md](4-mmr-seedgen.md). The two share only the stub mechanics at
the bottom of each file.

## How it was rolled at SGL25

Not automated, and not attempted. Wind Waker ran off a second Windows box in the
tournament room where **the players rolled their own seeds** from the desktop
app, choosing their own settings. Admins never saw the seed.

## What we know

- The tool is the **wwrando desktop app**, tournament fork
  [`tanjo3/wwrando`](https://github.com/tanjo3/wwrando). Season builds are tagged
  (`s7-v1` for 2024; `s8-v1` and `s8-v2` exist for Season 8).
- Settings travel as a **base64 permalink**. A 2024-season example:
  `eJwz1DM00DOIt7RITrQwM2VwZLhrVMTF0czAwMDCAAUcIEKAgYGJg3GlykMQAyoRwuLAsmajv8G85QwMk/iB6jUB5s8MHw==`
- SGL25 ran **Season 8 settings**. The exact build tag is not recorded.
- The bracket was community-owned rather than SpeedGaming's:
  <https://challonge.com/om2r4dwz>.
- **Per-player customisation is cosmetic only.** What has to be shared is a
  single string carrying the gameplay seed; colours and models are per-player.
  The permalink format enforces exactly this split — every option in the
  `#region Cosmetic` block of `options/wwrando_options.py` is declared
  `permalink=False`, so cosmetics are structurally absent from the string both
  players paste.

## What the repo answers

Checked against tag `s8-v2` of `tanjo3/wwrando` (2026-08-03).

- **There is a headless CLI.** `wwrando.py` builds an `argparse` parser with
  `--noui` ("skip loading GUI, randomize immediately with saved settings"),
  `--permalink` ("use the seed and options from the specified permalink"),
  `--seed`, and `--dry` ("randomize in-memory and write logs only, do not read
  or write any ISOs"). `run_no_ui()` calls
  `WWRandomizer.decode_permalink(args.permalink, options)` and never imports Qt.
  The test suite already drives it this way (`test/test_dry.py` →
  `make_argparser().parse_args(["--dry"])` + `WWRandomizer(...)`).
- **Caveat: `run_no_ui` still reads `settings.yaml` first**, unconditionally, for
  `clean_iso_path` and `output_folder` — even with `--permalink`. A headless
  deployment needs that file pre-seeded. Not a blocker, just not zero-config.
- **A permalink is a shareable string, and the ISO build is separate.** The
  format (`randomizer.py:525-599`) is
  `base64(zlib(VERSION + "\0" + seed + "\0" + packed_option_bytes))`. Decoding
  the 2024 example above yields version `1.10.0_98ca865`, seed `A`, 61 option
  bytes — and re-compressing it reproduces the original string byte for byte.
- **So rolling a seed needs no wwrando checkout, no ISO, and no sidecar.** Given
  the season's reference permalink, a new seed is: decompress, `split(b"\0", 2)`,
  swap the middle field, recompress, base64. Pure stdlib, a handful of lines —
  the `wwr` generator returns a string and stores nothing. Compare
  [`mmr`](4-mmr-seedgen.md), which needs a mounted ROM and a .NET sidecar.
- **Permalinks are version-locked**, so the season's build tag is part of the
  preset. `decode_permalink` raises `PermalinkWrongVersionError` /
  `PermalinkWrongCommitError` when `VERSION` does not match, and the version is
  the first field in the encoded blob — which means a stored permalink also
  *tells* us which build it belongs to.

## Open questions

1. Which **Season 8 permalink** did SGL25 use? Not recorded; it has to come from
   the organizers. The build tag is recoverable from the permalink itself, so
   this is one question rather than two, and it is the only thing blocking an
   implementation.
2. Is there a **hosted generator** upstream? Worth knowing, but not blocking —
   the seed-swap above needs no service.
3. Do players need anything beyond the permalink to start, such as a **seed
   hash** for an on-stream "same seed?" check? `WWRandomizer.get_seed_hash()`
   exists; whether the community uses it that way is unconfirmed.

## If the stub is promoted

The mechanics are already documented — see
[Adding a randomizer](../reference/seed-generation.md#adding-a-randomizer-or-preset)
and the stub-promotion note. In short: replace the `ValueError` body, drop `wwr`
from `STUB_RANDOMIZERS`, commit the season permalink under `presets/wwr/`, and
add `wwr` to `PRESET_AWARE_RANDOMIZERS` so the generator reads `preset.settings`
— omit that last one and it silently rolls its committed default forever. No
`CredentialSpec` is needed: nothing here is key-gated.
`AVAILABLE_RANDOMIZERS` and the dispatch map already list it.
