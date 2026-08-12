import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { surfaceStrings } from './bankSurfaces.js'
import { BANK_SURFACES } from './bankSurfaceInventory.js'

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')

/** Read the whole Bank tree as it is NOW — discovered, not listed, so a file
 *  the redesign creates is scanned without anyone remembering to add it. */
function bankTree() {
  const dirs = ['src/components/bank', 'src/components/videobank']
  const files = [
    'src/pages/BankPage.jsx',
    'src/pages/VideoBankPage.jsx',
    ...dirs.flatMap((d) => readdirSync(resolve(FRONTEND, d), { recursive: true })
      .filter((f) => String(f).endsWith('.jsx'))
      .map((f) => `${d}/${String(f).replaceAll('\\', '/')}`)),
  ]
  return files.map((f) => readFileSync(resolve(FRONTEND, f), 'utf8')).join('\n')
}

function occurrences(text) {
  const counts = new Map()
  for (const s of surfaceStrings(text)) counts.set(s, (counts.get(s) || 0) + 1)
  return counts
}

test('every interactive surface the Bank had before the redesign still exists', () => {
  const present = occurrences(bankTree())
  const lost = BANK_SURFACES
    .filter(([label, count]) => (present.get(label) || 0) < count)
    .map(([label, count]) => `${label}  (expected ${count}, found ${present.get(label) || 0})`)
  assert.deepEqual(lost, [],
    `Interactive surfaces disappeared from the Bank:\n  ${lost.join('\n  ')}`)
})

test('the inventory is not empty, which would make the guard vacuous', () => {
  // It froze 188 distinct surfaces. A collapse to a handful means the extractor
  // broke, and a guard that silently stops covering anything is worse than none.
  assert.ok(BANK_SURFACES.length > 150,
    `only ${BANK_SURFACES.length} surfaces frozen — the extractor probably broke`)
})
