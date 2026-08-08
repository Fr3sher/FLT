// Reads the image Bank TREE, not one file: the Encre redesign split the
// workspace into a top bar, a filter rail, a passes panel and the grid, and a
// wiring assertion must survive a move (see bankTreeSource.js).
import { bankTreeSource } from './bankTreeSource.js';
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const app = readFileSync(new URL('../../App.jsx', import.meta.url), 'utf8')
const page = readFileSync(new URL('../../pages/BankPage.jsx', import.meta.url), 'utf8')
const workspace = bankTreeSource()
const facets = readFileSync(new URL('./bankFacets.js', import.meta.url), 'utf8')
const overview = readFileSync(new URL('./BankOverview.jsx', import.meta.url), 'utf8')

test('/bank shares the wide 1800px shell with Canvas', () => {
  assert.match(app, /pathname === '\/canvas' \|\| pathname === '\/bank'/)
  assert.match(app, /max-w-\[1800px\]/)
})

test('bank list grows to three columns only at xl', () => {
  assert.match(page, /grid-cols-1 sm:grid-cols-2 xl:grid-cols-3/)
})

test('the four-megapixel resolution bucket is inclusive in the workspace too', () => {
  // The resolution tiers are a DATA table now (bankFacets.js), shared by the
  // filter rail and the tiles — assert them where they are defined.
  assert.match(facets, /id: 'res_gt_4', label: '≥ 4 MP'/)
  assert.doesNotMatch(facets, /id: 'res_gt_4', label: '> 4 MP'/)
})

test('the rail sits beside the grid, and folds instead of squeezing it', () => {
  /* This used to assert the FOUR-ZONE STACK: two twelve-column xl grids pairing
     Analyze with the overview and Curate with Promote. The Encre redesign
     replaced that stack on purpose — scrolling up to a filter and back down to
     its result was the actual complaint — so the invariant is rewritten, not
     relaxed. What has to stay true is the same thing it always protected: the
     screen is a single column on a phone and uses the width on a desktop.

     Two columns, not twelve: the rail has one job and a fixed measure, so a
     twelve-column grid would only be a more expensive way of writing 17rem. */
  assert.match(workspace, /sm:grid-cols-\[17rem_minmax\(0,1fr\)\]/)
  // …and it really does collapse to one column rather than shrinking the grid.
  assert.match(workspace, /railOpen && railIsColumnNow/)
  assert.match(workspace, /: 'grid-cols-1'/)
  // At 400 px the rail is a drawer OVER the grid, with a backdrop that closes it.
  assert.match(workspace, /isDrawer=\{!railIsColumnNow\}/)
  assert.match(workspace, /railOpen && !railIsColumnNow && \(/)

  // The passes panel keeps the twelve-column pairing: the action list and the
  // read-only overview answer the same question and belong side by side.
  const panel = readFileSync(new URL('./BankPassesPanel.jsx', import.meta.url), 'utf8')
  assert.match(panel, /grid gap-4 xl:grid-cols-12 xl:items-start/)
  assert.match(panel, /xl:col-span-7/)
  assert.match(panel, /xl:col-span-5/)
  assert.match(panel, /<BankOverview payload=\{payload\} \/>/)
})

test('overview never opens the expensive kept-only coverage endpoint', () => {
  const panel = readFileSync(new URL('./BankPassesPanel.jsx', import.meta.url), 'utf8')
  const overviewMount = panel.slice(panel.indexOf('<BankOverview'),
    panel.indexOf('<BankOverview') + 200)
  assert.doesNotMatch(overviewMount, /coverage/)
})

test('non-zero Bank segments use exact widths and remain physically visible', () => {
  assert.match(overview, /width: `\$\{row\.widthPercent\}%`/)
  assert.match(overview, /minWidth: row\.value > 0 \? '1px'/)
  assert.match(page, /width: `\$\{row\.widthPercent\}%`, minWidth: '1px'/)
  assert.doesNotMatch(page, /width: `\$\{row\.percent\}%`/)
})

test('the overview is open by default and folds without tying its state to live payload refreshes', () => {
  assert.match(overview, /const \[open, setOpen\] = useState\(true\)/)
  assert.match(overview, /onClick=\{\(\) => setOpen\(\(value\) => !value\)\}/)
  assert.match(overview, /aria-expanded=\{open\}/)
  assert.match(overview, /aria-controls=\{contentId\}/)
  assert.match(overview, /<div id=\{contentId\} hidden=\{!open\}/)
  assert.doesNotMatch(overview, /useState\([^)]*payload/)
})

test('the overview header and live total stay visible while its details fold', () => {
  const detailsAt = overview.indexOf('<div id={contentId}')
  assert.ok(detailsAt > 0)
  assert.ok(overview.indexOf('📊 Bank overview') < detailsAt)
  assert.ok(overview.indexOf('{totalText}') < detailsAt)
})

test('the overview has an explicit unavailable state before bank data arrives', () => {
  assert.match(overview, /!model\.available \? \(/)
  assert.match(overview, /Overview unavailable — waiting for bank data/)
  assert.match(overview, /'Total unavailable'/)
})
