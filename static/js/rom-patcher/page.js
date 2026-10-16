/*
 * The browser half of the ROM patch pages (pages/rom_patch.py): a hosted
 * patch at /patch/<token>, and the open patcher at /patcher.
 *
 * ROMs never leave the browser. Each one a player picks is kept in IndexedDB
 * on this device, keyed by its CRC32, so the next patch made for the same ROM
 * finds it without asking. An IPS names no ROM, so a hosted IPS remembers the
 * ROM by the game staff named instead. Picking files and downloading run from
 * the button's own click and answer with an event; the Python side only
 * draws what those events say.
 */

import { applyPatch, crc32, crcHex, matchRom, PatchError, patchInfo } from './formats.js';

const DB_NAME = 'wiz-rom-patcher';
const STORE = 'roms';
const GAMES_KEY = 'wiz-rom-patcher-games';

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

function games() {
  try {
    return JSON.parse(localStorage.getItem(GAMES_KEY) || '{}') || {};
  } catch (e) {
    return {};
  }
}

function rememberGame(game, key) {
  try {
    localStorage.setItem(GAMES_KEY, JSON.stringify({ ...games(), [game]: key }));
  } catch (e) {
    // Private windows can refuse storage; the ROM is still used for this visit.
  }
}

async function savedRom(key) {
  if (!key) return null;
  try {
    return (await dbGet(key)) || null;
  } catch (e) {
    return null;
  }
}

async function keepRom(entry) {
  try {
    await dbPut(entry.crc, entry);
  } catch (e) {
    // As above: the ROM works for this visit even if it can't be kept.
  }
}

function failure(e) {
  if (e instanceof PatchError) return { ok: false, error: e.message };
  console.error(e);
  return { ok: false, error: 'Something went wrong patching the ROM. Try again, or pick your ROM again.' };
}

function extension(name) {
  const m = /\.[A-Za-z0-9]{1,5}$/.exec(name || '');
  return m ? m[0] : '.bin';
}

function baseName(name) {
  return (name || 'patched').replace(/\.[A-Za-z0-9]{1,5}$/, '') || 'patched';
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

async function fetchBytes(url) {
  const resp = await fetch(url, { credentials: 'same-origin' });
  if (!resp.ok) throw new PatchError('fetch', `Couldn't load the patch (${resp.status}). Try again.`);
  return new Uint8Array(await resp.arrayBuffer());
}

function chooseFile(accept, onFile) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = accept;
  input.hidden = true;
  input.addEventListener('change', async () => {
    const file = input.files && input.files[0];
    input.remove();
    if (file) onFile(file, new Uint8Array(await file.arrayBuffer()));
  });
  document.body.appendChild(input);
  input.click();
}

function romSummary(entry) {
  return entry ? { name: entry.name, crc: entry.crc } : null;
}

const ROM_ACCEPT = '.sfc,.smc,.nes,.fds,.gb,.gbc,.gba,.n64,.z64,.v64,.gen,.md,.bin,.sms,.gg,.pce,.iso,application/octet-stream';

/**
 * Turns a picked file into a saved ROM entry for a patch that wants
 * `sourceCrc` (a number, or null when the patch names no ROM).
 */
function romEntry(name, bytes, sourceCrc) {
  const matched = matchRom(bytes, sourceCrc);
  if (!matched) {
    throw new PatchError(
      'source',
      `The ROM you picked is CRC32 ${crcHex(crc32(bytes))}. This patch needs ${crcHex(sourceCrc)}, `
        + 'usually a different region or revision.',
    );
  }
  return { name, crc: crcHex(sourceCrc ?? crc32(matched)), bytes: matched };
}

// --- A hosted patch: window.__wizRomPatch = {patchUrl, sourceCrc, game, outputBase}

function hosted(config) {
  const sourceCrc = config.sourceCrc ? parseInt(config.sourceCrc, 16) >>> 0 : null;
  const romKey = () => (sourceCrc != null ? crcHex(sourceCrc) : games()[config.game]);

  return {
    async status() {
      return { ok: true, rom: romSummary(await savedRom(romKey())) };
    },

    pickRom() {
      chooseFile(ROM_ACCEPT, async (file, bytes) => {
        let result;
        try {
          const entry = romEntry(file.name, bytes, sourceCrc);
          await keepRom(entry);
          if (sourceCrc == null) rememberGame(config.game, entry.crc);
          result = { ok: true, rom: romSummary(entry) };
        } catch (e) {
          result = failure(e);
        }
        window.emitEvent('rom_picked', result);
      });
      return { ok: true };
    },

    async download() {
      let result;
      try {
        const rom = await savedRom(romKey());
        if (!rom) {
          result = { ok: false, error: 'Pick your ROM first.', needRom: true };
        } else {
          const patched = applyPatch(await fetchBytes(config.patchUrl), rom.bytes);
          save(patched, `${config.outputBase}${extension(rom.name)}`);
          result = { ok: true };
        }
      } catch (e) {
        result = failure(e);
      }
      window.emitEvent('rom_download_done', result);
    },
  };
}

// --- The open patcher: the player brings both files.

function open() {
  const current = { patch: null, patchName: null, info: null, rom: null };

  return {
    pickPatch() {
      chooseFile('.bps,.ips,.ups,application/octet-stream', async (file, bytes) => {
        let result;
        try {
          const info = patchInfo(bytes);
          Object.assign(current, { patch: bytes, patchName: file.name, info, rom: null });
          if (info.sourceCrc != null) current.rom = await savedRom(crcHex(info.sourceCrc));
          result = {
            ok: true,
            name: file.name,
            format: info.format,
            crc: info.sourceCrc != null ? crcHex(info.sourceCrc) : null,
            rom: romSummary(current.rom),
          };
        } catch (e) {
          result = failure(e);
        }
        window.emitEvent('patch_picked', result);
      });
      return { ok: true };
    },

    pickRom() {
      chooseFile(ROM_ACCEPT, async (file, bytes) => {
        let result;
        try {
          if (!current.info) throw new PatchError('order', 'Pick the patch first.');
          const entry = romEntry(file.name, bytes, current.info.sourceCrc);
          if (current.info.sourceCrc != null) await keepRom(entry);
          current.rom = entry;
          result = { ok: true, rom: romSummary(entry) };
        } catch (e) {
          result = failure(e);
        }
        window.emitEvent('rom_picked', result);
      });
      return { ok: true };
    },

    async download() {
      let result;
      try {
        if (!current.patch || !current.rom) throw new PatchError('order', 'Pick a patch and a ROM first.');
        save(applyPatch(current.patch, current.rom.bytes), `${baseName(current.patchName)}${extension(current.rom.name)}`);
        result = { ok: true };
      } catch (e) {
        result = failure(e);
      }
      window.emitEvent('rom_download_done', result);
    },
  };
}

const config = window.__wizRomPatch || {};
const api = config.mode === 'hosted' ? hosted(config) : open();
window.wizRomPatcher = api;
if (window.__wizRomPatcherResolve) window.__wizRomPatcherResolve(api);
