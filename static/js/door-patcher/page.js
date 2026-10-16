/*
 * The browser half of the door seed page (pages/door_seed.py).
 *
 * The player's ROM never leaves the browser: it is kept in IndexedDB on this
 * device, and the seed ROM is built here and saved as a download. Options live
 * in localStorage so the next seed reuses them. The Python side reads and
 * writes through ui.run_javascript, so those methods resolve (never reject) to
 * plain data; picking a ROM and downloading run from the button's own click
 * and answer with an event instead.
 */

import { bpsSourceCrc, crc32 } from './bps.js';
import { adjustRom, buildSeedRom, parseSprite, RomError, stripHeader } from './patcher.js';

const DB_NAME = 'wiz-door-patcher';
const STORE = 'files';
const ROM_KEY = 'jp10';
const OPTIONS_KEY = 'wiz-door-patcher-options';

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function dbGet(key) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const req = db.transaction(STORE).objectStore(STORE).get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function dbPut(key, value) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function fetchBytes(url, what) {
  const resp = await fetch(url, { credentials: 'same-origin' });
  if (!resp.ok) throw new RomError('fetch', `Couldn't load the ${what} (${resp.status}). Try again.`);
  return new Uint8Array(await resp.arrayBuffer());
}

function failure(e) {
  if (e instanceof RomError) return { ok: false, error: e.message };
  console.error(e);
  return { ok: false, error: 'Something went wrong building the ROM. Try again, or pick your ROM again.' };
}

function save(bytes, filename) {
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

async function pickSprite(choice, spritesUrl) {
  if (!choice || choice.default) return null;
  if (!choice.random) return choice;
  const resp = await fetch(spritesUrl, { credentials: 'same-origin' });
  const sprites = resp.ok ? (await resp.json()).filter(s => !s.default) : [];
  return sprites.length ? sprites[Math.floor(Math.random() * sprites.length)] : null;
}

async function buildAndSave(seedInfo, options) {
  const rom = await dbGet(ROM_KEY);
  if (!rom) return { ok: false, error: 'Pick your ROM first.', needRom: true };
  const sprite = await pickSprite(options.sprite, seedInfo.spritesUrl);
  const [seed, base, spriteBytes] = await Promise.all([
    fetchBytes(seedInfo.patchUrl, 'seed').then(b => JSON.parse(new TextDecoder().decode(b))),
    fetchBytes(seedInfo.baseUrl, 'base patch'),
    sprite ? fetchBytes(sprite.file, 'sprite') : null,
  ]);
  const built = buildSeedRom(rom, base, seed.patch);
  adjustRom(built, options, spriteBytes ? parseSprite(spriteBytes) : null);
  save(built, seedInfo.filename);
  return { ok: true, sprite: sprite ? sprite.name : null };
}

let input = null;

const api = {
  async hasRom() {
    try {
      return { ok: true, hasRom: Boolean(await dbGet(ROM_KEY)) };
    } catch (e) {
      return { ok: true, hasRom: false };
    }
  },

  /** Opens the file picker; the answer arrives as the `door_rom_picked` event. */
  pickRom() {
    if (!input) {
      input = document.createElement('input');
      input.type = 'file';
      input.accept = '.sfc,.smc,application/octet-stream';
      input.hidden = true;
      input.addEventListener('change', async () => {
        const file = input.files && input.files[0];
        input.value = '';
        if (!file) return;
        let result;
        try {
          const bytes = stripHeader(new Uint8Array(await file.arrayBuffer()));
          const base = await fetchBytes(window.__wizDoorSeed.baseUrl, 'base patch');
          if (crc32(bytes) !== bpsSourceCrc(base)) {
            throw new RomError('version', 'That ROM is not the Japanese 1.0 release. Door Randomizer needs that one.');
          }
          await dbPut(ROM_KEY, bytes);
          result = { ok: true };
        } catch (e) {
          result = failure(e);
        }
        window.emitEvent('door_rom_picked', result);
      });
      document.body.appendChild(input);
    }
    input.click();
    return { ok: true };
  },

  loadOptions() {
    try {
      return { ok: true, options: JSON.parse(localStorage.getItem(OPTIONS_KEY) || 'null') };
    } catch (e) {
      return { ok: true, options: null };
    }
  },

  saveOptions(options) {
    try {
      localStorage.setItem(OPTIONS_KEY, JSON.stringify(options));
    } catch (e) {
      // Private windows can refuse storage; the page still works for this visit.
    }
    return { ok: true };
  },

  /**
   * Builds and saves the seed ROM from this page's seed (window.__wizDoorSeed:
   * {patchUrl, baseUrl, spritesUrl, filename}) and the saved options. Runs
   * straight from the button's click, so Safari still counts the save as one
   * the player asked for. The outcome arrives as the `door_download_done` event.
   */
  async downloadCurrent() {
    let result;
    try {
      result = await buildAndSave(window.__wizDoorSeed, api.loadOptions().options || {});
    } catch (e) {
      result = failure(e);
    }
    window.emitEvent('door_download_done', result);
  },
};

window.wizDoorPatcher = api;
if (window.__wizDoorPatcherResolve) window.__wizDoorPatcherResolve(api);
