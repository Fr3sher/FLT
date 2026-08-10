/**
 * EVERY SMALL PICTURE ASKS FOR A SMALL FILE.
 *
 * `/api/dataset/<id>/img/<name>` serves the ORIGINAL bytes — a 1-4 megapixel PNG
 * decoded in full to paint a 40 px avatar. The board, the dataset grid, the sweep
 * tiles and the run cards were moved onto `/thumb/?s=` in the performance wave;
 * these four surfaces were listed as remaining and are converted here.
 *
 * The assertions are on the RENDERED markup, not on the source text, because the
 * mistake this guards against is not "the helper is missing from the file" — it
 * is "the helper is imported but the URL that reaches `src` is still the
 * original", which only the output can answer. A companion assertion checks the
 * ORIGINAL is what a full-size surface keeps, so nobody fixes a future 404 by
 * rewriting every URL in sight.
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { createElement, renderToStaticMarkup } from './support/mountJsx.mjs'

const { MemoryRouter } = await import('react-router')
const { default: DatasetListPanel } = await import(
  '../src/components/dataset/DatasetListPanel.jsx')
const { default: RecentPrompts } = await import(
  '../src/components/dataset/studio/RecentPrompts.jsx')
const { datasetThumbUrl } = await import('../src/utils/datasetThumbUrl.js')

// These panels carry a HelpBadge, which reads the router — mount them in one.
const render = (Component, props) => renderToStaticMarkup(
  createElement(MemoryRouter, null, createElement(Component, props)))

const srcsOf = (html) => [...html.matchAll(/<img[^>]*\ssrc="([^"]+)"/g)].map((m) => m[1])
const datasetImgSrcs = (html) => srcsOf(html).filter((s) => s.includes('/api/dataset/'))

test('a library card and a library row ask for a thumbnail, never the original', () => {
  const datasets = [{
    id: 7, name: 'Aurora', ref_filename: 'cover.png',
    images_kept: 12, images_total: 12, kind: 'character',
  }]
  for (const view of ['grid', 'list']) {
    const html = render(DatasetListPanel, {
      datasets, view, showPreviews: true,
      onOpen: () => {}, onCreate: () => {}, onRefresh: () => {},
    })
    const srcs = datasetImgSrcs(html)
    assert.ok(srcs.length > 0, `${view}: no dataset picture rendered at all`)
    for (const src of srcs) {
      assert.match(src, /\/thumb\/[^?]+\?.*\bs=\d+/,
        `${view}: a cover still asks for the original — ${src}`)
      assert.doesNotMatch(src, /\/img\//, `${view}: ${src}`)
    }
  }
})

test('the recent-prompts strip draws thumbnails too', () => {
  const html = render(RecentPrompts, {
    datasetId: 7, items: [{ prompt: 'a portrait', thumbnail: 'thumb.png', count: 4 }],
    selectedPrompt: null, onPick: () => {}, onDelete: () => {},
  })
  const srcs = datasetImgSrcs(html)
  assert.ok(srcs.length > 0, 'recent-prompts: no picture rendered')
  for (const src of srcs) {
    assert.match(src, /\/thumb\/[^?]+\?.*\bs=\d+/, `recent-prompts: ${src}`)
  }
})

test('every dataset picture in these files is routed through the rewrite', async () => {
  /* BestPerModelList and the concept face-mask preview are collapsed / behind a
     pass by default, so no state this renderer can reach draws their pictures.
     They are pinned on the source instead — a weaker assertion, said plainly:
     it proves the URL is built through the helper, not what `src` ends up as. */
  const { readFile } = await import('node:fs/promises')
  for (const file of [
    '../src/components/dataset/studio/BestPerModelList.jsx',
    '../src/components/dataset/ConceptFaceMaskField.jsx',
  ]) {
    const src = await readFile(new URL(file, import.meta.url), 'utf8')
    const raw = [...src.matchAll(/`\/api\/dataset\/\$\{[^`]*\}\/img\/[^`]*`/g)]
    assert.ok(raw.length > 0, `${file}: no dataset image URL left to check — did it move?`)
    for (const m of raw) {
      const before = src.slice(Math.max(0, m.index - 40), m.index)
      assert.match(before, /datasetThumbUrl\($/,
        `${file}: a dataset image URL is built without datasetThumbUrl — ${m[0]}`)
    }
  }
})

test('the rewrite still refuses anything that is not a dataset image URL', () => {
  // The load-bearing half: a surface that shows something else must not be
  // silently pointed at an endpoint that cannot serve it.
  assert.equal(datasetThumbUrl('/api/bank/3/img/9', 128), '/api/bank/3/img/9')
  assert.equal(datasetThumbUrl('blob:whatever', 128), 'blob:whatever')
  assert.equal(datasetThumbUrl(null, 128), null)
})
