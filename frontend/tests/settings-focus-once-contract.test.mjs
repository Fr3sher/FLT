/**
 * The ?focus= reveal fires ONCE PER ARRIVAL — not once per config edit.
 *
 * The reveal effect must depend on `config` (the target field only exists
 * after the active section has rendered), and that dependency is exactly how
 * it went wrong: the section EDITS that object — every generation-LoRA preset
 * row added, every slider moved — and each edit re-ran the reveal, yanking
 * the reader back to the ?focus= field at the other end of a long section
 * (reported from Settings ▸ Image engines, mid preset editing, on a tablet).
 *
 * The contract, in source, because the guard is three lines a refactor could
 * drop without failing anything else:
 *   • the arrival key is (location.key, section, focusId) — a NEW navigation,
 *     even to the same URL, re-reveals; a re-render of the same visit never;
 *   • the guard is written only AFTER resolveFocusTarget succeeds, so a field
 *     that renders late still gets its one reveal when config lands;
 *   • location.key sits in the dependency list, or a same-URL re-navigation
 *     could not re-fire at all.
 */
import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'

const page = fs.readFileSync(
  new URL('../src/pages/SettingsPage.jsx', import.meta.url), 'utf8')

test('the reveal keys on the arrival, and skips a re-render of the same visit', () => {
  assert.match(page, /const arrival = `\$\{location\.key\}\|\$\{section\}\|\$\{focusId\}`/)
  assert.match(page, /if \(revealedRef\.current === arrival\) return undefined/)
})

test('the guard is only written once the target actually resolved', () => {
  const start = page.indexOf('if (revealedRef.current === arrival) return undefined')
  const end = page.indexOf('}, [focusId, section, loading, config, location.key])', start)
  assert.ok(start >= 0 && end > start, 'reveal effect not found')
  const effect = page.slice(start, end)
  assert.match(effect, /const reveal = \(found\) => \{\s*revealedRef\.current = arrival/)
  assert.equal((effect.match(/revealedRef\.current = arrival/g) || []).length, 1)
  assert.match(effect, /const found = resolveFocusTarget\(focusId\)\s*if \(found\) return reveal\(found\)/)
  assert.match(effect, /const late = resolveFocusTarget\(focusId\)\s*if \(late\) \{\s*clearInterval\(waiter\)\s*cleanup = reveal\(late\)/)
  assert.equal((effect.match(/reveal\((?:found|late)\)/g) || []).length, 2,
    'both immediate and lazy targets arm the guard only after resolution')
})

test('a fresh navigation to the same URL still re-reveals (location.key in deps)', () => {
  assert.match(page, /\}, \[focusId, section, loading, config, location\.key\]\)/)
})
