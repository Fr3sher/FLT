import { registerBundledDescriptor } from '../../../frontend/tests/support/bundledDescriptors.mjs'
// The plugin's descriptor and the partition it implies: what moved here is not
// in the core any more, and the core lends exactly the slot it says it does.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import descriptor from '../frontend/index.js'
import { resetRegistry, contributions } from '../../../frontend/src/plugins/registry.js'
import { parityGaps } from '../../../frontend/src/plugins/parity.js'
import { WORKSPACE_SECTIONS, sectionPanels } from '../../../frontend/src/components/dataset/workspaceSections.js'
import { getWorkspacePanels } from '../../../frontend/src/components/dataset/workspaceNavigation.js'
import { HF_EXPORT_ROW, hfExportAvailable } from '../frontend/lib/hfExport.js'

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')
const core = (rel) => read(`../../../frontend/src/${rel}`)

const CONTEXT = { kind: 'character', hasSelectableImages: true, hasKeptImages: true, hasCaptionedKept: true,
  hasLeakMetadata: false, watermarkDetected: 0, watermarkRejectable: 0, smallImageRescue: 0, unused: 0,
  trainingVisible: false, trainingStatusReady: true, trainingQueueCount: 0, studioVisible: false }

test('the publisher contributes its export row and its own token settings', () => {
  resetRegistry()
  assert.ok(registerBundledDescriptor(descriptor))
  const rows = contributions('export.action', 'dataset')
  assert.equal(rows.length, 1)
  assert.equal(rows[0].id, HF_EXPORT_ROW.id)
  assert.equal(rows[0].targetId, 'ds-export-hugging-face', 'the anchor the sidebar and the guide jump to')
  assert.equal(rows[0].when, hfExportAvailable)
  assert.equal(contributions('lightbox.action').length, 0)
  assert.equal(contributions('settings.group').length, 1)
  assert.equal(contributions('settings.group')[0].id, 'hf-publish-token')
  assert.deepEqual(contributions('settings.credential.help'), [], 'write-scope advice belongs to this product')
  assert.deepEqual(parityGaps(descriptor), [], 'a single-surface slot: no parity to keep')
  resetRegistry()
})

test('the active row stays discoverable before token or image preparation', () => {
  assert.equal(hfExportAvailable({ caps: { hf_publish: true }, hasKeptImages: true }), true)
  assert.equal(hfExportAvailable({ caps: { hf_publish: false }, hasKeptImages: true }), true)
  assert.equal(hfExportAvailable({ caps: {}, hasKeptImages: true }), true, 'missing token offers setup')
  assert.equal(hfExportAvailable({ caps: { hf_publish: true }, hasKeptImages: false }), true)
  assert.equal(hfExportAvailable(undefined), false)
})

test('the core rail lists the row through its section, under the same predicate', () => {
  resetRegistry()
  const exportSection = WORKSPACE_SECTIONS.find((s) => s.id === 'export')
  const ids = (ctx) => getWorkspacePanels('export', ctx).map((p) => p.id)
  assert.deepEqual(ids({ ...CONTEXT, caps: { hf_publish: true } }), ['import', 'training-zip', 'to-bank', 'backup'],
    'plugin off: the core rows only')
  registerBundledDescriptor(descriptor)
  assert.ok(sectionPanels(exportSection).some((p) => p.id === 'hugging-face'))
  assert.deepEqual(ids({ ...CONTEXT, caps: { hf_publish: true } }),
    ['import', 'training-zip', 'to-bank', 'backup', 'hugging-face'])
  assert.deepEqual(ids({ ...CONTEXT, caps: {} }), ['import', 'training-zip', 'to-bank', 'backup', 'hugging-face'], 'no token: setup is discoverable')
  assert.deepEqual(ids({ ...CONTEXT, caps: { hf_publish: true }, hasKeptImages: false }),
    ['import', 'training-zip', 'to-bank', 'backup', 'hugging-face'], 'nothing kept: preparation is discoverable')
  resetRegistry()
})

// The partition, on the frontend: the core's files that hosted the publisher
// lend a slot now and know nothing of Hugging Face publishing — not the
// dialog, not the row, not the capability it keys on.
const CORE_FILES_FREE_OF_PUBLISHING = [
  'components/dataset/DatasetWorkspace.jsx',
  'components/dataset/workspaceSections.js',
  'components/dataset/workspaceNavigation.js',
]

test('the core files that host the publisher name none of it', () => {
  const needle = /PublishHfModal|publishHf|hf_publish|hfPublish|huggingFace|Hugging Face|hugging-face/
  for (const rel of CORE_FILES_FREE_OF_PUBLISHING) {
    const hit = core(rel).match(needle)
    assert.equal(hit, null, `${rel}: still carries the publisher ("${hit && hit[0]}")`)
    assert.doesNotMatch(core(rel), /bundled\/hf_publish/, `${rel}: imports from the plugin`)
  }
  // The workspace lends the slot inside "More ways out" and reads the plugins'
  // summaries for the disclosure's line.
  const workspace = core('components/dataset/DatasetWorkspace.jsx')
  assert.match(workspace, /<PluginSlot slot="export\.action" surface="dataset"/)
  assert.match(workspace, /contributions\('export\.action', 'dataset'\)/)
  // The raw-fetch allowlist no longer names the dialog: it left the core.
  assert.doesNotMatch(read('../../../frontend/tests/direct-fetch-discipline.contract.test.mjs'), /PublishHfModal/)
})

test('the plugin mounts its dialog from the row, portaled out of the disclosure', () => {
  const row = read('../frontend/panels/HfExportAction.jsx')
  assert.match(row, /if \(!dataset \|\| !hfExportAvailable\(context\)\) return null/, 'the row and the rail agree')
  assert.match(row, /createPortal\(\s*<PublishHfModal datasetId=\{dataset\.id\}/)
  assert.match(row, /id=\{HF_EXPORT_ROW\.targetId\}/)
})
