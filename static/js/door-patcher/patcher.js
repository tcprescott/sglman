/*
 * Builds a Door Randomizer seed ROM in the browser, from the player's own
 * Japanese 1.0 ROM. Nothing here touches the network or the page: the caller
 * fetches the base patch, the seed's writes and any sprite, and hands bytes in.
 *
 *   buildSeedRom(rom, basePatch, writes)  -> Uint8Array
 *   adjustRom(rom, options, sprite)       -> rom, adjusted in place
 *   parseSprite(bytes)                    -> {sprite, palette, gloves}
 *
 * The addresses mirror the randomizer's own Rom.apply_rom_settings, so a ROM
 * made here matches what the randomizer would write with the same settings.
 */

import { applyBps, BpsError } from './bps.js';
import { randomize as randomizePalettes } from '../vendor/z3pr/z3pr.esm.js';

const ROM_SIZE = 0x200000;
const JP10_SIZE = 0x100000;

export class RomError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

export const DEFAULT_OPTIONS = Object.freeze({
  heartBeep: 'normal',
  heartColor: 'red',
  menuSpeed: 'normal',
  quickswap: true,
  music: true,
  reduceFlashing: false,
  owPalettes: 'default',
  uwPalettes: 'default',
});

export const CHOICES = Object.freeze({
  heartBeep: ['off', 'quarter', 'half', 'normal', 'double'],
  heartColor: ['red', 'blue', 'green', 'yellow', 'random'],
  menuSpeed: ['half', 'normal', 'double', 'triple', 'quadruple', 'instant'],
  owPalettes: ['default', 'shuffled', 'legacy', 'grayscale', 'blackout', 'puke'],
  uwPalettes: ['default', 'shuffled', 'legacy', 'grayscale', 'blackout', 'puke'],
});

/** The player's ROM without a copier header, or a RomError saying why not. */
export function stripHeader(bytes) {
  if (bytes.length % 0x400 === 0x200) bytes = bytes.subarray(0x200);
  if (bytes.length !== JP10_SIZE) {
    throw new RomError('size', 'That file is not a Link to the Past ROM: it is the wrong size.');
  }
  return bytes;
}

export function buildSeedRom(romFile, basePatch, writes) {
  const source = stripHeader(romFile);
  let rom;
  try {
    rom = applyBps(basePatch, source);
  } catch (e) {
    if (e instanceof BpsError && e.code === 'source') {
      throw new RomError('version', 'That ROM is not the Japanese 1.0 release. Door Randomizer needs that one.');
    }
    throw e;
  }
  if (rom.length < ROM_SIZE) {
    const grown = new Uint8Array(ROM_SIZE);
    grown.set(rom);
    rom = grown;
  }
  for (const [address, bytes] of Object.entries(writes)) {
    const at = Number(address);
    if (!Number.isInteger(at) || at < 0 || !Array.isArray(bytes)) {
      throw new RomError('patch', 'The seed patch is damaged.');
    }
    if (at + bytes.length > rom.length) {
      const grown = new Uint8Array(at + bytes.length);
      grown.set(rom);
      rom = grown;
    }
    rom.set(bytes, at);
  }
  return rom;
}

const MENU_SPEED = { instant: 0xE8, double: 0x10, triple: 0x18, quadruple: 0x20, half: 0x04, normal: 0x08 };
const HEART_BEEP = { off: 0x00, half: 0x40, quarter: 0x80, normal: 0x20, double: 0x10 };
const HEART_COLOR = { red: 0, blue: 1, green: 2, yellow: 3 };
const PALETTE_MODE = {
  shuffled: 'maseya', legacy: 'classic', grayscale: 'grayscale', blackout: 'blackout', puke: 'puke',
};

export function adjustRom(rom, options = {}, sprite = null, random = Math.random) {
  const o = { ...DEFAULT_OPTIONS, ...options };

  const instant = o.menuSpeed === 'instant';
  rom[0x6DD9A] = instant ? 0x20 : 0x11;
  rom[0x6DF2A] = instant ? 0x20 : 0x12;
  rom[0x6E0E9] = instant ? 0x20 : 0x12;
  rom[0x180048] = MENU_SPEED[o.menuSpeed] ?? MENU_SPEED.normal;

  rom[0x18004B] = o.quickswap ? 0x01 : 0x00;

  const off = !o.music;
  rom[0x0CFE18] = off ? 0x00 : 0x70;
  rom[0x0CFEC1] = off ? 0x00 : 0xC0;
  rom.set(off ? [0x00, 0x00] : [0xDA, 0x58], 0x0D0000);
  rom.set(off ? [0xC4, 0x58] : [0xDA, 0x58], 0x0D00E7);
  rom[0x18021A] = off ? 0x01 : 0x00;

  rom[0x180033] = HEART_BEEP[o.heartBeep] ?? HEART_BEEP.normal;
  let color = o.heartColor;
  if (color === 'random') color = ['red', 'blue', 'green', 'yellow'][Math.floor(random() * 4)];
  rom[0x187020] = HEART_COLOR[color] ?? HEART_COLOR.red;

  if (o.reduceFlashing) rom[0x18017F] = 1;

  if (sprite) {
    rom.set(sprite.sprite, 0x80000);
    if (sprite.palette) rom.set(sprite.palette, 0xDD308);
    if (sprite.gloves) rom.set(sprite.gloves, 0xDEDF5);
  }
  writeCredits(rom, sprite ? sprite.author : 'Nintendo');

  const seed = () => Math.floor(random() * 0x100000000);
  if (PALETTE_MODE[o.owPalettes]) {
    randomizePalettes(rom, { randomize_overworld: true, mode: PALETTE_MODE[o.owPalettes], seed: seed() });
  }
  if (PALETTE_MODE[o.uwPalettes]) {
    randomizePalettes(rom, { randomize_dungeon: true, mode: PALETTE_MODE[o.uwPalettes], seed: seed() });
  }

  writeChecksum(rom);
  return rom;
}

/** The SNES header checksum, as the randomizer writes it. */
export function writeChecksum(rom) {
  let sum = 0;
  for (let i = 0; i < rom.length; i++) {
    if (i < 0x7FDC || i >= 0x7FE0) sum += rom[i];
  }
  const crc = (sum + 0x01FE) & 0xFFFF;
  const inv = crc ^ 0xFFFF;
  rom.set([inv & 0xFF, inv >> 8, crc & 0xFF, crc >> 8], 0x7FDC);
}

const CREDIT_LETTERS = ' 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const CREDIT_PUNCTUATION = { "'": [0xD9, 0xEC], '.': [0xDC, 0xEF], '/': [0xDB, 0xEE], ':': [0xDD, 0xF0], _: [0xDE, 0xF1] };

function creditBytes(ch) {
  if (ch === ' ') return [0x9F, 0x9F];
  if (CREDIT_PUNCTUATION[ch]) return CREDIT_PUNCTUATION[ch];
  const i = CREDIT_LETTERS.indexOf(ch);
  return i > 0 ? [0x52 + i, 0x78 + i] : [0x9F, 0x9F];
}

function writeCredits(rom, author) {
  const name = String(author || '').slice(0, 28).toUpperCase();
  const left = Math.floor((28 - name.length) / 2);
  const padded = ' '.repeat(left) + name + ' '.repeat(28 - name.length - left);
  for (let i = 0; i < 28; i++) {
    const [top, bottom] = creditBytes(padded[i]);
    rom[0x118002 + i] = top;
    rom[0x118020 + i] = bottom;
  }
}

/**
 * A sprite from a .zspr file, or a raw 0x7000/0x7078/0x707C dump. A missing
 * palette or glove colours leave Link's own in place.
 */
export function parseSprite(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const isZspr = bytes.length > 0x1D && String.fromCharCode(...bytes.subarray(0, 4)) === 'ZSPR';
  let sprite, palette, gloves, author = '';
  if (isZspr) {
    const spriteAt = view.getUint32(9, true);
    const spriteSize = view.getUint16(13, true);
    const paletteAt = view.getUint32(15, true);
    const paletteSize = view.getUint16(19, true);
    if (spriteSize !== 0x7000 || spriteAt + spriteSize > bytes.length || paletteAt + paletteSize > bytes.length) {
      throw new RomError('sprite', 'That sprite file is damaged.');
    }
    sprite = bytes.slice(spriteAt, spriteAt + spriteSize);
    if (paletteSize >= 0x78) palette = bytes.slice(paletteAt, paletteAt + 0x78);
    if (paletteSize >= 0x7C) gloves = bytes.slice(paletteAt + 0x78, paletteAt + 0x7C);
    author = zsprAuthor(bytes);
  } else if ([0x7000, 0x7078, 0x707C].includes(bytes.length)) {
    sprite = bytes.slice(0, 0x7000);
    if (bytes.length >= 0x7078) palette = bytes.slice(0x7000, 0x7078);
    if (bytes.length === 0x707C) gloves = bytes.slice(0x7078, 0x707C);
  } else {
    throw new RomError('sprite', 'That is not a sprite file.');
  }
  return {
    sprite,
    palette: palette || null,
    gloves: gloves || null,
    author,
  };
}

// After the 29-byte header: display name and author in UTF-16LE, each
// null-terminated, then the author again in ASCII for the credits.
function zsprAuthor(bytes) {
  let at = 0x1D;
  const skipUtf16 = () => {
    while (at + 1 < bytes.length && (bytes[at] || bytes[at + 1])) at += 2;
    at += 2;
  };
  skipUtf16();
  skipUtf16();
  let end = at;
  while (end < bytes.length && bytes[end]) end++;
  return String.fromCharCode(...bytes.subarray(at, Math.min(end, at + 64)));
}
