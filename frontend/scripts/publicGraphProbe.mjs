// Source graph qualification only: never writes bundles or distribution files.
import { build } from 'esbuild'
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const root = path.resolve(fileURLToPath(new URL('../..', import.meta.url)))
const result = await build({
  absWorkingDir: root, entryPoints: ['frontend/src/main.jsx'], bundle: true,
  write: false, outdir: 'frontend/.graph-not-written', metafile: true, format: 'esm', packages: 'external',
  loader: { '.png': 'dataurl', '.jpg': 'dataurl', '.svg': 'dataurl', '.md': 'text' },
  plugins: [{ name: 'raw-source-only', setup(plugin) {
    plugin.onResolve({ filter: /\?raw$/ }, args => ({ path: path.resolve(args.resolveDir, args.path.slice(0, -4)), namespace: 'raw' }))
    plugin.onLoad({ filter: /.*/, namespace: 'raw' }, args => ({ contents: readFileSync(args.path, 'utf8'), loader: 'text' }))
  } }],
})
const output = process.argv[2]
if (output) writeFileSync(output, JSON.stringify(result.metafile, null, 2))
console.log(`Core source graph resolved: ${Object.keys(result.metafile.inputs).length} modules; no build artifact written.`)
