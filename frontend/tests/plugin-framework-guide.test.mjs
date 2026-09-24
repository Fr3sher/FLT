import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { CORE_GUIDE_ANCHORS } from '../src/help/guideHosts.js'
import { composeGuide, findGuideChapter, guideHeadings, validateGuide } from '../src/plugins/guideContent.js'
import { guideChapters, registerDescriptor, resetRegistry, setEnabled } from '../src/plugins/registry.js'

const FILES = { 'getting-started': 'guide/getting-started.md', 'using-the-app': 'guide/using-the-app.md',
  'dataset-guide': 'DATASET_GUIDE.md', 'settings-reference': 'guide/settings-reference.md',
  troubleshooting: 'guide/troubleshooting.md', 'getting-help': 'guide/getting-help.md' }
const core = Object.entries(FILES).map(([id, path]) => ({ id,
  source: fs.readFileSync(new URL(`../../docs/${path}`, import.meta.url), 'utf8') }))
const ownership = { chapters: ['example.reader.manual'], sections: ['example.reader.manual#example-guide', 'settings-reference#example-setting'] }
const example = text => ({ id: 'example.reader', guide: {
  chapters: [{ id: 'example.reader.manual', title: 'Example guide', description: 'Installed help' }],
  sections: [{ chapter: 'example.reader.manual', anchor: 'example-guide', markdown: `## Example guide\n\n${text}\n` },
    { chapter: 'settings-reference', anchor: 'example-setting', markdown: '## Example setting\n\nCalibrate the example tool.\n' }],
} })

test('reserved anchors correspond to public Markdown, not a private anchor catalogue', () => {
  assert.deepEqual(Object.keys(CORE_GUIDE_ANCHORS), Object.keys(FILES))
  for (const chapter of core) assert.deepEqual(CORE_GUIDE_ANCHORS[chapter.id], guideHeadings(chapter.source))
  assert.deepEqual(guideHeadings('## Visible\r\n```\r\n## Hidden\r\n```\r\n'), ['visible'])
})

test('a namespaced installed guide appears only when its owner is enabled', () => {
  resetRegistry()
  const before = JSON.stringify(core)
  assert.equal(registerDescriptor(example('Installed contents'), { guideOwnership: ownership }), true)
  setEnabled(['example.reader'])
  assert.match(findGuideChapter(guideChapters(core), 'example.reader.manual').source, /Installed contents/)
  assert.equal(findGuideChapter(guideChapters(core), 'missing.manual'), null)
  setEnabled([])
  assert.equal(findGuideChapter(guideChapters(core), 'example.reader.manual'), null)
  assert.equal(JSON.stringify(core), before, 'core Markdown is not rewritten by composition')
})

test('undeclared content and collisions cannot replace core or another owner', () => {
  const valid = example('Contents')
  assert.match(validateGuide(valid, [], undefined), /ownership/)
  assert.equal(validateGuide(valid, [], ownership), null)
  assert.match(validateGuide(valid, [valid], ownership), /collision/)
  const bad = example('Contents')
  bad.guide.sections[1] = { chapter: 'settings-reference', anchor: CORE_GUIDE_ANCHORS['settings-reference'][0],
    markdown: `## ${core.find(c => c.id === 'settings-reference').source.match(/^## (.+)$/m)[1]}\n\nCannot replace core.\n` }
  assert.match(validateGuide(bad, [], ownership), /collision/)
  assert.equal(composeGuide(core, []).length, core.length)
})

test('nested headings, insertion anchors and manifest ownership are checked together', () => {
  const bad = example('Contents')
  bad.guide.sections[1].after = 'anchor-not-in-public-guide'
  assert.match(validateGuide(bad, [], ownership), /existing core anchor/)
  delete bad.guide.sections[1].after
  bad.guide.sections[0].markdown += '\n### Example setting\n'
  assert.equal(validateGuide(bad, [], ownership), null, 'anchors belong to chapters')
  bad.guide.sections[1].markdown += '\n## Another top-level section\n'
  assert.match(validateGuide(bad, [], ownership), /one matching H2/)
})
