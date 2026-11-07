// Runs the frontend tests of every bundled plugin (bundled/*/tests/*.test.js).
//
// `node --test` only discovers tests under its working directory and refuses
// a directory argument outside it, and a `**` glob typed in PowerShell is
// expanded one level deep (see CLAUDE.md) — so the files are listed here and
// handed to node explicitly. Run from frontend/:  npm run test:bundled
import { readdirSync, existsSync } from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const BUNDLED = path.resolve(HERE, '..', '..', 'bundled')

const files = []
if (existsSync(BUNDLED)) {
  for (const plugin of readdirSync(BUNDLED, { withFileTypes: true })) {
    if (!plugin.isDirectory()) continue
    const dir = path.join(BUNDLED, plugin.name, 'tests')
    if (!existsSync(dir)) continue
    for (const f of readdirSync(dir)) {
      if (/\.test\.(m?js)$/.test(f)) files.push(path.join(dir, f))
    }
  }
}
if (!files.length) {
  console.log('no bundled plugin tests found')
  process.exit(0)
}
console.log(`bundled plugin tests: ${files.length} file(s)`)
const res = spawnSync(process.execPath, ['--import', pathToFileURL(path.join(HERE, 'registerSdk.mjs')).href, '--test', ...files], { stdio: 'inherit' })
process.exit(res.status ?? 1)
