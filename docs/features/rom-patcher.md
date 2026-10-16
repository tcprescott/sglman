# ROM patcher

Two pages that patch a player's own ROM in their browser, built on the same engine as the [door seed page](../reference/seed-generation.md#alttprdr). No ROM ever reaches the server.

| Page | Who uses it | What it does |
|---|---|---|
| `/t/<slug>/patch/<token>` | anyone with the link | A patch staff host. Shows what it needs (game, CRC32), then **Choose your ROM…** the first time and **Download patched ROM** after that. |
| `/t/<slug>/patcher` | anyone | The player brings a BPS, IPS or UPS file and a ROM. Nothing is uploaded or stored on the server. |
| Admin → Patches | STAFF, `PRESET_MANAGER` | Upload a patch, then share its link. Row ⋮: Copy link, Open page, Edit, Replace file…, Delete…. |

Decisions (Thomas, 2026-10-16): patches come from **both** places (hosted links and the open page); staff upload under **Admin → Patches** (layout A), not on the tournament; **no feature flag**.

## How it fits together

- **Model.** `RomPatch` (tenant-scoped): title, the ROM it needs (`game`), format, `source_crc`, optional tournament, download count. See [data-model.md](../reference/data-model.md#rompatch).
- **Files.** `RomPatchStore` writes `<token>.<format>` under `ROM_PATCH_DIR` (default `rom-patches/` on the door seed volume). `/rom-patches/<token>/<version>` serves it; the page puts the patch's `updated_at` in `<version>`, so a replaced file is fetched fresh.
- **Checking an upload.** `application/utils/rom_patch_format.read_patch` refuses anything that isn't a BPS (`BPS1`), UPS (`UPS1`) or IPS (`PATCH`), checks a BPS/UPS's own checksum, walks an IPS to its `EOF`, and reads the source CRC32 a BPS/UPS stores in its footer. An IPS names no ROM, so staff may type the CRC; a BPS/UPS's own CRC always wins over a typed one.
- **Service.** `RomPatchService` (see [services.md](../reference/services.md#rom_patch_servicepy--rompatchservice)), audited, no events.
- **Browser engine.** `static/js/rom-patcher/formats.js` applies all three formats behind `applyPatch(patch, rom)`, reusing `door-patcher/bps.js` for BPS. `matchRom` drops a 512-byte copier header when that is what stands between the ROM and the patch's CRC. A wrong ROM is refused with both CRCs in the message.
- **Remembering ROMs.** `page.js` keeps every ROM a player picks in IndexedDB (`wiz-rom-patcher` / `roms`), keyed by the CRC32 of the bytes the patch used. The next patch made for the same ROM finds it without asking, on either page. A hosted IPS without a CRC remembers the ROM by its `game` text instead (localStorage `wiz-rom-patcher-games`).
- **Downloads.** The page reports each finished download back, and `RomPatchService.record_download` bumps the count shown in Admin → Patches.

## Dev and tests

`scripts/seed_online.py` seeds two patches per community: `dev-patch-<slug>` (a BPS made for 1 MB of zero bytes, the same stand-in ROM as the door seed: `head -c 1048576 /dev/zero > dev-rom.sfc`) and `dev-ips-<slug>` (an IPS with no CRC). Tests: `tests/services/test_rom_patch_service.py`, `tests/tenancy/test_rom_patch_tenant_isolation.py`, and `tests/js/rom_patcher.test.mjs` (run under Node by `tests/test_door_patcher_js.py`).
