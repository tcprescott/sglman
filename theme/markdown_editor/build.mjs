// Bundles src/index.mjs into dist/index.js (one ES module NiceGUI serves via
// `esm=`) and writes dist/THIRD_PARTY_LICENSES.txt from every bundled package.
import { build } from 'esbuild';
import { readFileSync, readdirSync, existsSync, writeFileSync, rmSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

rmSync('dist', { recursive: true, force: true });
mkdirSync('dist');

const result = await build({
  entryPoints: ['src/index.mjs'],
  bundle: true,
  format: 'esm',
  minify: true,
  legalComments: 'none',
  target: 'es2020',
  outfile: 'dist/index.js',
  metafile: true,
});

const packages = new Set();
for (const input of Object.keys(result.metafile.inputs)) {
  const m = input.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
  if (m) packages.add(m[1]);
}

const notices = [];
for (const name of [...packages].sort()) {
  const dir = join('node_modules', name);
  const pkg = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'));
  const licenseFile = readdirSync(dir).find((f) => /^licen[cs]e/i.test(f));
  const text = licenseFile ? readFileSync(join(dir, licenseFile), 'utf8').trim() : `License: ${pkg.license}`;
  notices.push(`${name}@${pkg.version} (${pkg.license})\n\n${text}`);
}
writeFileSync(
  'dist/THIRD_PARTY_LICENSES.txt',
  `Third-party software bundled into dist/index.js\n\n${notices.join('\n\n' + '-'.repeat(72) + '\n\n')}\n`,
);
console.log(`bundled ${packages.size} packages`);
