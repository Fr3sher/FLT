import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { VIDEO_PASS_TOPICS } from "../../../../bundled/video/frontend/videobank/videoPassTopics.js"
import { PASS_LABELS } from "../../../../bundled/video/frontend/videobank/videoBankStatus.js"
import { getHelpTopic } from '../../help/helpRegistry.js'
import { markdownHeadingId } from '../../utils/headingId.js'

import videoPlugin from '../../../../bundled/video/frontend/index.js'
import { registerDescriptor, resetRegistry, setEnabled } from '../../plugins/registry.js'
test.beforeEach(() => {
  resetRegistry()
  const manifest = JSON.parse(readFileSync(new URL('../../../../bundled/video/plugin.json', import.meta.url), 'utf8'))
  assert.equal(registerDescriptor(videoPlugin, { guideOwnership: manifest.guide_ownership }), true)
  setEnabled(['video'])
})
test.afterEach(() => resetRegistry())

/* These ids live in a plain object, not in quoted JSX topic attributes, so the
   help-registry contract's source scan never sees them. This is the equivalent
   check: every pass button has a mapped section, every mapped id resolves, and
   every anchor is a real H2 of its chapter — an ⓘ that opens an empty modal is
   worse than no ⓘ at all. */

test('every pass button has a topic, and every topic resolves', () => {
  for (const pass of Object.keys(PASS_LABELS)) {
    const topic = VIDEO_PASS_TOPICS[pass]
    assert.ok(topic, `pass "${pass}" has no info topic`)
    assert.ok(getHelpTopic(topic), `pass "${pass}": unknown topic "${topic}"`)
  }
})

test('every mapped anchor is a real H2 of its chapter', () => {
  const cache = new Map()
  const anchorsOf = (chapter) => {
    if (!cache.has(chapter)) {
      const md = readFileSync(fileURLToPath(new URL(
        chapter === 'dataset-guide'
          ? '../../../../docs/DATASET_GUIDE.md'
          : `../../../../docs/guide/${chapter}.md`, import.meta.url)), 'utf8').replace(/\r\n/g, '\n')
      const owned = videoPlugin.guide.sections.filter(section => section.chapter === chapter).map(section => section.markdown).join('\n')
      cache.set(chapter, new Set(
        [...`${md}\n${owned}`.matchAll(/^##\s+(.+)$/gm)].map((m) => markdownHeadingId(m[1]))))
    }
    return cache.get(chapter)
  }
  for (const [pass, topic] of Object.entries(VIDEO_PASS_TOPICS)) {
    const t = getHelpTopic(topic)
    assert.ok(anchorsOf(t.guide.chapter).has(t.guide.anchor),
      `pass "${pass}": anchor #${t.guide.anchor} is not an H2 of ${t.guide.chapter}`)
  }
})
