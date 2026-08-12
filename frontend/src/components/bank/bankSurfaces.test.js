import assert from 'node:assert/strict'
import test from 'node:test'
import { surfaceStrings } from './bankSurfaces.js'

test('reads the label out of a button', () => {
  assert.deepEqual(surfaceStrings('<button type="button">🚀 Launch all…</button>'),
    ['🚀 Launch all…'])
})

test('reads aria-label and title', () => {
  const src = '<button aria-label="Remove bank" title="Removes triage data only">✕</button>'
  assert.deepEqual(surfaceStrings(src).sort(),
    ['Removes triage data only', 'Remove bank', '✕'].sort())
})

test('keeps the literal label of a button carrying a conditional suffix', () => {
  // The shape almost every pass button in this codebase has. The first version
  // of the extractor skipped these entirely — the guard was covering only the
  // buttons nobody would have lost.
  const src = "<button onClick={open}>✨ Score…{!caps.bank_scoring && ' (needs setup)'}</button>"
  assert.deepEqual(surfaceStrings(src), ['✨ Score…'])
})

test('keeps a label wrapped in nested markup', () => {
  const src = '<button><span className="x">Open</span> →</button>'
  assert.deepEqual(surfaceStrings(src), ['Open', '→'])
})

test('a whole label is one entry, never split into words', () => {
  // An inventory of single words matches anything, so it would stay green on a
  // Bank that had lost the button.
  assert.deepEqual(surfaceStrings('<button>Select all in filter</button>'),
    ['Select all in filter'])
})

test('a fully computed label yields nothing, since no frozen string could match it', () => {
  assert.deepEqual(surfaceStrings('<button>{captionLabel(n)}</button>'), [])
})

test('an arrow function in an attribute does not end the opening tag', () => {
  // "<button[^>]*>" stops at the ">" of "=>", so the body used to start
  // mid-attribute and the inventory filled up with className fragments.
  const src = '<button onClick={() => open(b.id)} className="truncate">Open →</button>'
  assert.deepEqual(surfaceStrings(src), ['Open →'])
})

test('a self-closing button contributes no body', () => {
  assert.deepEqual(surfaceStrings('<button aria-label="Close" onClick={() => x()} />'),
    ['Close'])
})

test('drops syntax leftovers but keeps symbol-only labels', () => {
  const src = '<button>{cond ? ( <span>Keep</span> ) : ( <span>Reject</span> )}</button>'
    + '<button aria-label="Close">✕</button><button>▶ Review</button>'
  assert.deepEqual(surfaceStrings(src).sort(), ['Close', '▶ Review', '✕'].sort())
})

test('trims whitespace and drops empties', () => {
  assert.deepEqual(surfaceStrings('<button>\n   Open →\n  </button>'), ['Open →'])
})
