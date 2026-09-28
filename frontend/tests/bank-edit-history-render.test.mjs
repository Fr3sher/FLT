import assert from 'node:assert/strict'
import test from 'node:test'
import { render } from './support/mountJsx.mjs'
import { imageVersionQuery } from '../src/components/bank/bankEdits.js'

const { default: BankReviewLightbox } = await import('../src/components/bank/BankReviewLightbox.jsx')
const { default: BankEditComparison } = await import('../src/components/bank/BankEditComparison.jsx')

test('Review offers undo and comparison for saved history, not legacy edits', () => {
  const image = { id: 7, name: 'sample.webp', edit_method: 'improve', edit_generation: 2 }
  const props = { bankId: 1, ids: [7], seedImages: [image] }
  const legacy = render(BankReviewLightbox, props)
  assert.doesNotMatch(legacy, /Undo last edit|Compare before \/ after/)
  assert.match(legacy, /Revert all edits/)
  const current = render(BankReviewLightbox, {
    ...props, seedImages: [{ ...image, edit_history_count: 2, edit_sequence: 2 }],
  })
  assert.match(current, /Undo last edit/)
  assert.match(current, /Compare before \/ after/)
})

test('comparison loads the last input, not the uncropped original', () => {
  const html = render(BankEditComparison, {
    bankId: 1, image: { id: 7, edit_generation: 2, edit_sequence: 3 },
  })
  assert.match(html, /Before last edit/)
  assert.match(html, /Current version/)
  assert.match(html, /file\/7\?e=2&amp;v=3&amp;previous=1/)
  assert.doesNotMatch(html, /original=1/)
})

test('undo to the initial image still changes its thumbnail cache key', () => {
  assert.notEqual(imageVersionQuery({}), imageVersionQuery({ edit_sequence: 2 }))
  assert.notEqual(imageVersionQuery({ edit_generation: 1, edit_sequence: 1 }),
    imageVersionQuery({ edit_generation: 1, edit_sequence: 3 }))
})
