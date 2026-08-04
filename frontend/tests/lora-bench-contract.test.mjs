/* ⚖ LoRA bench — the page's contract.
 *
 * Two halves. The pure model (which strength wins, when we refuse to guess a
 * trigger, when the launch is blocked) is exercised for real. The JSX is read as
 * TEXT for the handful of promises that are easy to delete by accident — the
 * caveat under the grid, the folder hint in the empty state, the "no activation
 * word" escape hatch, and the fact that the run lifecycle is still the Studio's.
 * Reading source as text is a weak assertion and it is used only where a real
 * render would need the component tree mounted; everything with logic in it is
 * tested through the model instead.
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import {
  SWEEP_CAVEAT, bestStrength, cellsAt, filterLoras, groupByFamily, isLowConfidence,
  launchBlocker, runCheckpoint, scoreAt, strengthsOf, toggleStrength, triggerNotice,
} from '../src/pages/bench/benchModel.js'
import { helpTopics } from '../src/help/helpRegistry.js'
import { WHATS_NEW, isValidTarget } from '../src/whatsNew.js'

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')
const PAGE = read('../src/pages/BenchPage.jsx')
const APP = read('../src/App.jsx')

const LORAS = [
  { filename: 'krea\\civitai_thing.safetensors', name: 'civitai_thing.safetensors', family: 'krea', family_label: 'Krea 2' },
  { filename: 'sdxl\\lora_Mine_000001000.safetensors', name: 'lora_Mine_000001000.safetensors', family: 'sdxl', family_label: 'SDXL' },
]
const FAMILIES = [
  { family: 'zimage', label: 'Z-Image', folder: 'z image' },
  { family: 'sdxl', label: 'SDXL', folder: 'sdxl' },
  { family: 'krea', label: 'Krea 2', folder: 'krea' },
]

// ---- the picker ------------------------------------------------------------

test('the picker searches names and drops families with nothing in them', () => {
  assert.equal(filterLoras(LORAS, 'civitai').length, 1)
  assert.equal(filterLoras(LORAS, 'SDXL').length, 1)          // family label counts
  assert.equal(filterLoras(LORAS, '').length, 2)
  const groups = groupByFamily(LORAS, FAMILIES)
  assert.deepEqual(groups.map((g) => g.family), ['sdxl', 'krea'])   // zimage empty → gone
})

// ---- the grid --------------------------------------------------------------

test('the grid reads its strengths from the CELLS, not from the form', () => {
  // A cancelled or resumed run rendered fewer cells than were asked for; the
  // grid must show what exists, in order.
  const run = { cells: [{ strength: 1.0 }, { strength: 0.4 }, { strength: 1.0 }] }
  assert.deepEqual(strengthsOf(run), [0.4, 1.0])
  assert.equal(cellsAt(run, 1.0).length, 2)
  assert.deepEqual(strengthsOf(null), [])
})

test('the ★ follows the run on screen, not the file left selected in the picker', () => {
  // Open an earlier bench of another LoRA: the picker still shows whatever you
  // clicked last. Scoring the grid against THAT file would star a strength
  // measured for a different LoRA — a wrong answer that looks like a right one.
  const run = { cells: [{ strength: 0.4, checkpoint: 'krea\\old.safetensors' },
                        { strength: 0.8, checkpoint: 'krea\\old.safetensors' }] }
  assert.equal(runCheckpoint(run), 'krea\\old.safetensors')
  const scores = [
    { checkpoint: 'krea\\old.safetensors', strength: 0.4, rank: 0.7, voted: 3, images: 3 },
    { checkpoint: 'krea\\just_picked.safetensors', strength: 0.8, rank: 0.9, voted: 5, images: 5 },
  ]
  assert.equal(bestStrength(scores, runCheckpoint(run)), 0.4)   // not 0.8
  assert.equal(runCheckpoint(null), null)
  assert.equal(runCheckpoint({ cells: [] }), null)
})

test('no strength is crowned before anything has been voted on', () => {
  const ck = 'krea\\civitai_thing.safetensors'
  const unvoted = [
    { checkpoint: ck, strength: 0.4, rank: 0, voted: 0, images: 1, low_confidence: true },
    { checkpoint: ck, strength: 0.8, rank: 0, voted: 0, images: 1, low_confidence: true },
  ]
  // Every entry sits at rank 0, so a "best" would be pure tie-breaking order —
  // a verdict invented out of sort stability.
  assert.equal(bestStrength(unvoted, ck), null)
  assert.equal(isLowConfidence(unvoted, ck), false)

  const voted = [
    { checkpoint: ck, strength: 0.4, rank: 0.1, voted: 1, images: 1, low_confidence: true },
    { checkpoint: ck, strength: 0.8, rank: 0.6, voted: 2, images: 2, low_confidence: true },
  ]
  assert.equal(bestStrength(voted, ck), 0.8)
  assert.equal(isLowConfidence(voted, ck), true)   // thin: every entry under 3 votes
  assert.equal(scoreAt(voted, ck, 0.8).rank, 0.6)
  assert.equal(scoreAt(voted, 'other', 0.8), null) // another file's scores never bleed in
})

// ---- the trigger, the trap this feature exists to avoid ---------------------

test('a trigger is announced as read, never as certain — and never guessed', () => {
  const known = triggerNotice({ source: 'metadata', trigger: 'zoeydoll' })
  assert.equal(known.state, 'metadata')
  assert.match(known.text, /usually, but not always/)

  for (const info of [null, { source: null, trigger: '', candidates: [{ tag: '1girl' }] }]) {
    const unknown = triggerNotice(info)
    assert.equal(unknown.state, 'unknown')
    assert.match(unknown.text, /does not say/)
    // Says WHY it matters — otherwise the warning is noise and gets clicked past.
    assert.match(unknown.text, /never touched|reads as a bad LoRA|bad LoRA/)
  }
})

test('the launch is blocked, with a reason, until the trigger question is answered', () => {
  const base = { filename: 'krea\\x.safetensors', strengths: [0.8], trigger: '', noTrigger: false }
  assert.match(launchBlocker(base), /activation word/)
  assert.equal(launchBlocker({ ...base, noTrigger: true }), null)   // explicit escape hatch
  assert.equal(launchBlocker({ ...base, trigger: 'zoeydoll' }), null)
  assert.match(launchBlocker({ ...base, filename: null }), /Pick a LoRA/)
  assert.match(launchBlocker({ ...base, strengths: [] }), /at least one strength/)
  assert.match(launchBlocker({ ...base, trigger: 'x', running: true }), /still going/)
  // A busy GPU speaks for itself rather than being flattened into "cannot run".
  assert.equal(launchBlocker({ ...base, trigger: 'x', gpuBusy: 'LoRA training in progress' }),
    'LoRA training in progress')
})

test('the sweep caps instead of silently dropping a choice', () => {
  let list = []
  for (const v of [0.2, 0.4, 0.6, 0.8]) list = toggleStrength(list, v, 4)
  assert.deepEqual(list, [0.2, 0.4, 0.6, 0.8])
  assert.deepEqual(toggleStrength(list, 1.0, 4), list)      // refused at the cap
  assert.deepEqual(toggleStrength(list, 0.4, 4), [0.2, 0.6, 0.8])
  assert.deepEqual(toggleStrength([1.0, 0.2], 0.6, 8), [0.2, 0.6, 1.0])  // stays sorted
})

// ---- the promises the page makes -------------------------------------------

test('the grid says what it does NOT prove, in one sentence', () => {
  assert.match(SWEEP_CAVEAT, /not whether\s+.*the LoRA is good/s)
  assert.ok(SWEEP_CAVEAT.length < 220, 'the caveat must stay one sentence, not a paragraph')
  assert.ok(PAGE.includes('SWEEP_CAVEAT'), 'BenchPage must render the caveat')
})

test('the empty state names the folders instead of saying "nothing to show"', () => {
  // The hint text itself is built server-side (lora_bench.bench_folder_hint) so
  // the folder names cannot drift from the scanners; the page must render it.
  assert.match(PAGE, /loras\.length === 0/)
  assert.match(PAGE, /folder_hint/)
})

test('the page offers the no-activation-word escape hatch', () => {
  assert.match(PAGE, /This LoRA has no activation word/)
  assert.match(PAGE, /no_trigger: noTrigger/)
})

test('tag suggestions are labelled as tags, and are not prefilled', () => {
  assert.match(PAGE, /Most frequent training tags/)
  assert.match(PAGE, /often, but not always, the activation word/)
})

test('the bench owns no second run lifecycle', () => {
  // Cancel goes to the STUDIO's route. A bench-specific cancel/resume endpoint
  // is how the two surfaces would begin to disagree about a run's state.
  assert.match(PAGE, /\/api\/studio\/run\/\$\{runId\}\/cancel/)
  assert.ok(!/\/api\/bench\/run\/[^'"`]*\/(cancel|resume|status)/.test(PAGE),
    'the bench must not grow its own run lifecycle routes')
})

test('the page is reachable and gated like the Test Studio', () => {
  assert.match(APP, /<Route path="\/bench" element=\{<BenchPage \/>\} \/>/)
  assert.match(APP, /caps\.studio_visible && \(\s*<NavLink to="\/bench"/)
  assert.match(PAGE, /if \(!caps\.studio_visible\)/)     // direct-URL guard too
})

test('the page has a help topic and a What\'s-new entry', () => {
  const topic = helpTopics.find((t) => t.id === 'page-bench')
  assert.ok(topic, 'page-bench topic missing from the help registry')
  assert.equal(topic.app.route, '/bench')
  assert.equal(topic.guide.chapter, 'using-the-app')
  assert.match(PAGE, /topic="page-bench"/)

  const entry = WHATS_NEW.find((e) => e.id === '2026-08-04-lora-bench-test-a-downloaded-lora')
  assert.ok(entry, 'What\'s-new entry missing')
  assert.ok(isValidTarget(entry.to), `${entry.to} is not a valid in-app target`)
})

test('the default sweep is written once on each side and must not drift', () => {
  // The page starts on a sweep before the first fetch answers, and the server
  // publishes the same list (lora_bench.DEFAULT_STRENGTHS) for the payload. Two
  // literals, so pin them together — a user who never touches the chips must
  // get the run the backend describes.
  assert.match(PAGE, /useState\(\[0\.4, 0\.6, 0\.8, 1\.0\]\)/)
  const py = read('../../backend/app/services/lora_bench.py')
  assert.match(py, /DEFAULT_STRENGTHS = \(0\.4, 0\.6, 0\.8, 1\.0\)/)
})

test('the sixth workspace cannot make the page scroll sideways', () => {
  // Measured on the real page at 768 px: the desktop nav row was ALREADY
  // saturated to the pixel with five workspaces, so adding ⚖ Bench pushed the
  // header to 838 px and the whole document scrolled horizontally. The fix is
  // the wrapping box around the workspace links — deleting it brings the bug
  // straight back, and nothing else in the file says why it is there.
  assert.match(APP, /flex min-w-0 flex-1 flex-wrap items-center gap-1/)
  // …and it must NOT be `overflow-x-auto`, which would clip the ? / ⚙ popovers.
  assert.ok(!/aria-label="Main navigation"[\s\S]{0,400}overflow-x-auto/.test(APP))
})

test('the results strip scrolls inside its own box, never the page', () => {
  // 400 px is the real reading width. A grid that widens the body makes the
  // whole page scroll sideways, which is how a phone layout breaks.
  assert.match(PAGE, /overflow-x-auto/)
})
