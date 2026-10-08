# SGL 2026 on-site randomizers

Research notes, not a plan: what each on-site tournament on the SGL 2026 planning sheet races on, read from that tournament's own rules doc (the **Rules** link on the sheet's `Onsite` tab) in October 2026. It exists so the randomizers can be settled before anything is written into `Tournament.randomizer_notes`. That field ships empty on purpose, and `scripts/import_sgl_tournaments.py` does not fill it. Delete this file after the event.

## Summary

| Tournament | Generator | Settings source | `seed_generator` | Wizzrobe preset (`sgl26`) | Wizzrobe can roll? |
|---|---|---|---|---|---|
| ALttP Any% NMG | none (vanilla) | — | — | — | n/a |
| ALttPR Hybrid Major Glitches | ALttPR doors branch | HMG logic, 7/7 open defeat Ganon; branch TBD | none | none | no |
| ALttP Randomizer | alttpr.com / SahasrahBot | SahasrahBot preset `openboots` | `alttpr` | **missing** (`casualboots`, `sglive2025` exist) | yes, once the preset exists |
| Donkey Kong 64 Randomizer | dk64randomizer.com | DK64R Season 5 race settings | `dk64r` | `Season 5 Race Settings` ✅ | yes (async roll) |
| Final Fantasy Randomizer | finalfantasyrandomizer.com | Flags link on the FFR wiki (v4.9.7) | `ff1r` | n/a (flags, not presets) | yes |
| Majora's Mask Randomizer | mmrandomizer.com | Generator preset `SGL 2026` | `mmr` | n/a | **no** (stub) |
| Ocarina of Time Randomizer | ootrandomizer.com (generatorDev) | Generator preset `SGL 2026 Tournament` | `ootr` | **outdated** (`sgl25`) | yes, once updated |
| Super Metroid Any% | none (vanilla) | — | — | — | n/a |
| Super Metroid Map Randomizer | maprando.com | `Community Race Season 5` preset | `smmap` | **outdated** (`community_race_s4`) | yes, once updated |
| Super Metroid: DASH | dashrando.net | Settings listed on the event page | `smdash` | n/a | **no** (stub) |
| The Legend of Zelda Randomizer | Z1R executable (Self Service) | Flag string | `z1r` | n/a | yes |
| Wind Waker Randomizer | tanjo3 wwrando build | Permalink + build `dev_tanjo3.1.10.7.3` | `wwr` | n/a | **no** (stub) |
| Best of NES (Relay, High Score) | none | — | — | — | n/a |

`seed_generator` is what the importer sets from the tournament name. "Stub" means `SeedGenerationService.STUB_RANDOMIZERS`: registered, but rolling raises. See [4-mmr-seedgen.md](4-mmr-seedgen.md) and [5-wwr-seedgen.md](5-wwr-seedgen.md).

## Open questions

- **ALttPR presets.** `openboots` doesn't exist in `sgl26` yet. Create it before anyone rolls from the schedule.
- **HMG branch.** The rules doc says the doors branch will be picked closer to the event, pending cavestate key-behaviour fixes. Nobody has confirmed which one yet.
- **FFR flags disagree.** The planning sheet's "Long Link" opens v4.8.6 (`s=47D73892`). The FFR wiki (the tournament's rules page) links v4.9.7 flags. Ask DarkmoonEX which is right.
- **WWR build disagrees.** The sheet links release `s8-v2`. The rules doc names build `dev_tanjo3.1.10.7.3` and an `s9-tournament` tracker. The rules doc looks current.
- **OoTR and SM Map presets are last year's.** `sgl25` → SGL 2026 Tournament; `community_race_s4` → Community Race Season 5.
- **SM Map screenshot is cropped.** The rules doc shows the preset as an image that stops at "Save the animals". Anything below that (QoL details, item progression tweaks) isn't in the doc, so assume the stock preset.
- **DK64 race rooms.** DK64R rolls asynchronously (`ASYNC_RANDOMIZERS`), so the seed is queued, not instant. Check that's acceptable for a proctor handing seeds out at the desk.

## Per tournament

### A Link to the Past Any% No Major Glitches
Vanilla, not a randomizer: Any% NMG, no save & quit, standard speedrun.com rules. One amendment: after any save & quit, return to the screen you saved on, then carry on with no penalty. Races run on racetime.gg/alttp, a proctor timer, or untimed side by side.

### A Link to the Past Randomizer Hybrid Major Glitches
- HMG logic, rolled as open, 7/7 crystals, defeat Ganon, on the ALttPR **doors** branch (exact branch TBD).
- Required: overworld OOB clips, plus Mire→Hera, Hera→Swamp, Ice Palace lobby, Kikiskip.
- Allowed, never required: underworld minor glitches, overworld mirrorless bunny clipping, fake flutes.
- Glitch ruleset, fair play and goal: HMG 2025 rules.

### A Link to the Past Randomizer
- SahasrahBot preset `openboots`: open mode, Pegasus Boots start.
- Group stage (groups of 5), then a top-16 Bo1 bracket.

### Donkey Kong 64 Randomizer
- DK64R Season 5 race settings, Glitchless ruleset. The full settings string is in the rules doc, and the `sgl26` preset `Season 5 Race Settings` matches it.
- Complex level order, vanilla bosses, all bananaports pre-activated.
- Start with Keys 2 and 6, Diving, Cranky, Funky, Snide, Progressive Slam, ammo belt and instrument upgrade, plus 3 random moves. Climbing is shuffled.
- Wrinkly doors hint, from custom static locations. Melon crates and half-medals are checks, and all filler is GBs. [Custom locations sheet](https://docs.google.com/spreadsheets/d/1Nnfgn7PdlCjY-n1cs1fuxp3bRsx3S-sYk5gmVdVnLtw/edit?gid=277924991#gid=277924991).
- Endgame: Helm B. Locker 50 GBs, back of Helm 64 GBs, Blast-O-Matic needs the Helm stars plus 2 rooms, then 3 K. Rool phases.
- PJ64 recommended. Everdrive runners get no lag head start.

### Final Fantasy Randomizer
- Flags: [FFR wiki "Tournament Flags" link](https://4-9-7.finalfantasyrandomizer.com/?s=00000000&f=7yYeU3NWYWa-shYkqHmG37-rS90EfpcUfUjp78ZR6KibBTdXQJnVpIePSloACp-y7pmGE2-q9cgwtGhrPz.mWHn.CIpIv7SBX0Cq6Q-JkRCpdP4JdINmzfSpJnbrJIUV7i9Zc0bReCbdLdiHKyjE6C-v9OEgBo-lQpuYWgo7KPkEA5Q58DLpK5GPOujIdXYCxVNLqv) (v4.9.7). The sheet has a different one; see open questions.
- Double elim Bo1, finals Bo3 with no winners'-bracket advantage. FFR General Rules & Guidance apply.

### Majora's Mask Randomizer
- mmrandomizer.com → Settings Presets → `SGL 2026` → Load. [Settings file](https://zsr.link/MMRSGL2026Settings).
- Start with sword, shield, Giant's Mask, Garo Mask, Song of Time, Song of Soaring, Goron Lullaby intro, Epona's Song.
- 3 remains for moon access. The Oath hint comes after the third dungeon if Oath to Order isn't found.
- Small keysy and boss keysy (boss key chests shuffled); quest items through time; overworld frogs, Swamp Archery #2 (double rewards) and milk bar purchases shuffled; a list of checks junked.
- Hints: 4 WOTH, 3 Foolish, 7 Always.
- Standard racing ruleset for tricks and emulator settings.

### Ocarina of Time Randomizer
- ootrandomizer.com (generatorDev branch), preset `SGL 2026 Tournament`; or a racetime room with custom goal `SGL 2026` and `!seed` (Mido's House). Elagatua's SGL branch for offline rolls.
- Bridge: 3 spiritual stones. Ganon's BK: Shadow + Spirit medallions, given on the LACS.
- Light medallion dungeon pre-completed; Forest medallion always on Link's Pocket.
- Adult start in the Temple of Time with Prelude and the song from Zelda, plus Farore's Wind and Lens of Truth. Free maps and compasses.
- Hints: 5 path, 4 foolish (ToT only, max 1 dungeon), 3 dual sometimes, 6 single sometimes, plus fixed always-hints.
- All Locations Reachable (new this year). Standard ruleset; new tricks banned until ruled on.
- The bracket runs on start.gg, which is why the importer doesn't link Challonge for this one.

### Super Metroid Any%
Vanilla, not a randomizer.

### Super Metroid Map Randomizer
- maprando.com, preset `Community Race Season 5`: skill Hard, objectives Bosses, map layout Standard, doors Ammo, random start, Save the Animals off.
- Latest stable version. If a new stable ships mid-event, later races move to it.
- Banned: OOB, ammo underflow, wrong warps, artificial items, memory corruption, grapple teleport or ice clips past the Mother Brain barriers. Auto-tracking is fine for items and bosses, not the map layout.

### Super Metroid: DASH
- dashrando.net: item split Major/Minor; area randomization; bosses shuffled and known; Double Jump, Pressure Valve and Heat Shield on; Charge Beam vanilla; ammo 3:2:1; environment Standard; gravity heat reduction off; standard logic; item fanfare on.
- Same glitch bans as Map Rando. Hitbox Samus sprite banned. Auto-tracking is fine for items and collected-item locations, not area portals.

### The Legend of Zelda Randomizer
- Flags `12TDBKH6mxLfnSz4T7ME4bcIaaUe9sE7UVmj7RA`, rolled with the executable at Self Service.
- 2nd-quest overworld, unsorted shapes dungeons, community hints. Level 9 needs 8 triforces, Ganon forced.
- 3 starting hearts; white sword at 4–6 hearts, magical sword at 12. Atlas book, started with. Extra candles; enemy HP ±2; most open stairs removed.
- **Reduced Flashing** flag mandatory for every race. No raft skip. Up+A on controller 2 is allowed for softlocks.

### Wind Waker Randomizer
- Build [`dev_tanjo3.1.10.7.3`](https://github.com/tanjo3/wwrando/releases/tag/dev_tanjo3.1.10.7.3), permalink:
  `eJxLSS2LL0nMy8o31jPUMzTQM9czjk8xNkgxMk9mcGS4//1Tc+mHA/HnJOY/kNiv9INfkeHfX/4/wgYMDA5PT/3n/K/J/ceehUGg4Ub9f3v/nE32d0rsjf//L663/v+fg5UBBBy8liYysDEJKDRdnfGzJYFHgIGJkYkFIsUgzODAWMCgxMMBAMVjLfw=`
- 3 required bosses, no starting sword, randomized dungeon entrances, random starting island, boss soul shuffle.
- KoRL hints: 3 path, 5 barren, 6 location. Kreeb hints the bows.
- Players may toggle enemy palettes and camera or sea-compass inversion.
- [Tracker](https://www.wooferzfg.me/tww-rando-tracker/s9-tournament/). Manual tracking only.

### Best of NES (Relay, High Score)
No rules doc or randomizer on the sheet yet.
