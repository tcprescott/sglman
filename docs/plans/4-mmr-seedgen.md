# Majora's Mask seed generation (`mmr`) — research notes

**Not a plan.** `mmr` is a registered stub in
[`seedgen_service.py`](../../application/services/seedgen_service.py) — selectable on a
tournament, present in every UI/API surface, and raising `ValueError` when
rolled. It was rolled by hand at SGL25. This file records how, and what promoting
the stub would cost, so the decision can be made before the September 2026
freeze.

Wind Waker is a separate problem with a separate answer:
[5-wwr-seedgen.md](5-wwr-seedgen.md). The two share only the stub mechanics at
the bottom of each file.

## How it was rolled at SGL25

A self-contained bundle, `MM-Randomizer-SGL.zip` (106 MB), was assembled for the
admin PCs: the randomizer CLI, the base ROM, one shared settings file, and a
per-player cosmetics folder for each of the fifteen entrants. Admins ran a batch
script, entered the two players' assigned numbers, and handed out the resulting
ROMs. Automating it was raised shortly before the event and deferred for lack of
time.

## What is inside the bundle

| Path | What it is |
|---|---|
| `MMR.CLI.exe` + `MMR.CLI.dll` | The randomizer CLI. Framework-dependent .NET (`tfm: net5.0`, `rollForward: LatestMinor`) |
| `MM Randomizer.exe` / `.dll` | The GUI, unused by the script |
| `sgl.json` | The tournament settings — one `GameplaySettings` object, ~180 keys |
| `1/` … `15/` | One folder per player: their `settings.json` (cosmetics) and their `music/` |
| `GAMER_NUMBERS.txt` | Maps each entrant to their numbered folder |
| `Legend of Zelda, The - Majora's Mask (U).z64` | The base ROM, 32 MB |
| `vc/` | `wadpacker` + keys, for Wii VC output |
| `output/` | Empty drop folder |

`sgl.json` is the settings we would need to commit as `presets/mmr/sgl.json`:
`LogicMode: Casual`, `VictoryMode: CantFightMajora, ThreeBossRemains`,
`RequiredBossRemains: 3`, `GossipHintStyle: Competitive`, 18 enabled tricks, and
the three packed `Custom*ListString` fields that carry the item pool.

## The actual command

`GENERATE_SEEDS.bat`, stripped of prompts and the retry loop:

```bat
:: 1. roll once, emit a patch (the .z64 it also writes is deleted immediately)
MMR.CLI.exe -settings sgl.json -output "output\P1_vs_P2.z64" -spoiler -outputpatch ^
            -input ".\Legend of Zelda, The - Majora's Mask (U).z64"

:: 2. per player: swap the cosmetics into the program root, re-apply the same patch
for %%F in (P1 P2) do (
    rd /s /q "%cd%\music"
    xcopy /E /I /Y "%%F\*" "%cd%\"
    MMR.CLI.exe -inputpatch "output\P1_vs_P2.mmr" -output "output\%%F.z64" -input %ROM%
)
```

**The `.mmr` patch is the seed.** Cosmetics are not part of the roll — they are a
second pass that re-patches the same `.mmr` with whatever `settings.json` and
`music/` happen to be sitting in the program root. One roll produces one
shareable artifact; cosmetics are a client-side concern.

Two properties of the script do not carry over to an automated context: the retry
loop is unbounded (`goto retry` on any non-zero exit), and the cosmetics pass
mutates the program root, so two concurrent runs would corrupt each other.

## Why the artifact route does not fit `SeedGenerationService`

Every generator in the dispatch map returns a **string** — a permalink from an
HTTP call, or a locally-built URL. `GeneratedSeeds.seed_url` is a text column and
the UI renders `^https?://` as a link and everything else as plain text
(`z1r` already exercises the plain-text path).

Rolling MMR the way SGL25 did produces a **binary artifact**: a `.mmr` patch, or
a `.z64`/`.wad` per player. The app has no file storage and nothing that serves a
download. Four consequences:

1. **Somewhere to run .NET.** `MMR.CLI.dll` is framework-dependent, so
   `dotnet MMR.CLI.dll …` should run on Linux under a .NET 8/9 runtime
   (`rollForward: LatestMinor`) — **untested**. The app image has no .NET today.
   Either add the runtime to the Dockerfile or stand the roller up as a sidecar
   the app calls over HTTP, which is the shape every other backend already
   assumes.
2. **The base ROM.** Generation needs `Majora's Mask (U).z64`, which cannot be
   shipped or stored in the repo or the image. It would have to be mounted as an
   operator-supplied file, a kind of deployment input the app has never had. The
   patch output carries no copyrighted data, so only the roller needs the ROM,
   not the players.
3. **Somewhere to put the output.** A `.mmr` is a few hundred KB and has to reach
   two players. Nothing in the app stores or serves files.
4. **Cosmetics.** Server-side rolling drops the per-player pass: the app would
   hand out one `.mmr` and players would patch locally with their own cosmetics,
   which the MMR GUI supports. That is a tournament-rules decision, not a
   technical one.

## The seed-number route

MMR takes a seed. `MMR.CLI.dll` documents `-seed` as "Set the seed for the
randomizer", and the GUI has the matching field (`tSeed`, label `Random seed:`,
rejected with "Invalid seed: must be a positive integer."). Same build + same
`GameplaySettings` + same integer produces the same game, and `sgl.json` already
sets `DrawHash: true`, so both players can compare the file-select hash icons to
confirm they match.

That is the `z1r` shape, and it removes all four blockers above. The app rolls a
random positive integer, stores it as a plain string in `seed_url` (the UI
already renders non-URL values as plain text), and DMs it to both players.
`_generate_mmr` becomes a few lines with no HTTP call, no ROM, no .NET, no
storage.

The settings split works in favour of this. `-settings` loads **only**
`GameplaySettings` ("Other settings will be loaded from your default
settings.json file"), so a player's cosmetics and music stay personal while the
ruleset stays shared — the same separation the `-outputpatch` / `-inputpatch`
dance achieved, reached without generating anything centrally.

Four conditions, in order of how likely they are to sink it:

1. **Players can read their own spoiler.** `-spoiler` is just a flag, so anyone
   rolling locally can re-roll with it and see the item placement. This is why
   SGL25 distributed finished ROMs. It is a tournament-integrity question for the
   organizers, not something code can fix — **settle it before building
   anything**.
2. **The importance-verification timeout may break determinism.**
   `-maxImportanceWait` skips item-importance verification after N seconds, and
   `sgl.json` sets `ImportanceCount: true` with hint priorities that depend on
   it. A check that completes on a fast machine and is skipped on a slow one
   could yield different hints from the same seed. Test before committing: roll
   one seed on two machines, compare hashes.
3. **Identical build.** A different MMR version places differently from the same
   seed. The bundle is the 2024-07-27 build; the assembly version reads
   `1.0.0.0`, so the build has to be pinned by distributing it rather than by
   number.
4. **Identical settings file.** `sgl.json` has to reach both players, which is an
   argument for committing it as a `Preset` under either route.

## Options, cheapest first

- **Leave the stub.** One batch script on one admin PC, as at SGL25. No work.
- **Register the settings only.** Commit `presets/mmr/sgl.json` and import it as
  a `Preset` so the ruleset is versioned in the repo rather than in a zip file,
  while rolling stays manual. Independent of which route below is taken.
- **Seed number.** The section above. No new infrastructure; gated on the spoiler
  question rather than on anything technical.
- **Sidecar roller.** A service wrapping `MMR.CLI.dll` with the ROM mounted,
  exposing `POST /roll` → patch URL; `_generate_mmr` becomes an ordinary HTTP
  generator and the envelope in `application/utils/seed_provider.py` applies
  unchanged. Keeps rolling central, so players never touch a spoiler flag. The
  largest option by a wide margin, and only warranted if condition 1 above rules
  out seed numbers.

## Open questions

1. Is a player self-rolling from a shared seed number acceptable for a
   tournament, given they could re-roll with `-spoiler`?
2. Does MMR have, or want, a hosted generator upstream? Rolling ROMs in our own
   infrastructure is a commitment worth avoiding if upstream is already heading
   there.
3. Does `-maxImportanceWait` affect determinism at these settings (condition 2)?

## If the stub is promoted

The mechanics are already documented — see
[Adding a randomizer](../reference/seed-generation.md#adding-a-randomizer-or-preset)
and the stub-promotion note. In short: replace the `ValueError` body, drop `mmr`
from `STUB_RANDOMIZERS`, add a `CredentialSpec` if the upstream is keyed, commit
the settings under `presets/mmr/`, and add `mmr` to `PRESET_AWARE_RANDOMIZERS` if
the generator reads `preset.settings` — omit that last one and it silently rolls
its committed default forever. `AVAILABLE_RANDOMIZERS` and the dispatch map
already list it.
