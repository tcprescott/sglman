# z3pr (vendored)

Palette shuffle for the door seed patcher (`static/js/door-patcher/patcher.js`).

- Source: [`@maseya/z3pr`](https://github.com/Maseya/z3pr-js) 1.0.1, unmodified,
  with its one dependency `lodash` 4.18.1.
- Licences: z3pr is LGPL-3.0-or-later (`LICENSE.md`); lodash is MIT
  (`LICENSE.lodash`). Wizzrobe is GPL-3.0, so serving the bundle is fine.
- npm ships z3pr as ES source only, so `z3pr.esm.js` is a plain esbuild bundle
  of it. To rebuild or upgrade:

```bash
mkdir z3pr-build && cd z3pr-build && npm init -y
npm install @maseya/z3pr@1.0.1 esbuild@0.24.0
echo "export { randomize } from '@maseya/z3pr';" > entry.js
npx esbuild entry.js --bundle --format=esm --minify --legal-comments=inline --outfile=z3pr.esm.js
```
