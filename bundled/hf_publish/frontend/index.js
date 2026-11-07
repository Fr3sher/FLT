import { GUIDE } from './guide.js'
// 🤗 Publish to Hugging Face — the frontend descriptor of the bundled
// `hf_publish` plugin. Plain JS on purpose: node --test imports it (the
// parity, help and slot contracts), Vite globs it at build time
// (src/plugins/bundled.js). The panel is a lazy import, its own chunk.
//
// ONE place the core lends: `export.action` — a row of the dataset
// workspace's Import & export section ("More ways out"). The core reads the
// row's data for its rail and deep links (`when` decides whether the row is
// offered on THIS dataset) and mounts the panel, which draws the button and
// its dialog. Dataset-only by nature: a Bank has no captions or trigger to
// publish, so the slot is single-surface (no parity to keep).
import { HF_EXPORT_ROW, hfExportAvailable } from './lib/hfExport.js'

export default {
  guide: GUIDE,
  id: 'hf_publish',
  nav: [],
  routes: [],
  slots: {
    'settings.group': [{ id: 'hf-publish-token', section: 'local-tools',
      title: 'Hugging Face publishing token', blurb: 'Authorize publishing to your dataset repository with the shared Hugging Face token.',
      keywords: ['hugging face', 'publish', 'token', 'write', 'repository'],
      panel: () => import('./panels/HfPublishSettings.jsx') }],
    'export.action': [
      { ...HF_EXPORT_ROW, when: hfExportAvailable, panel: () => import('./panels/HfExportAction.jsx') },
    ],
  },
  hosts: [],
  help: [{ id: 'hf-publish', kind: 'action', title: 'Publish a dataset to Hugging Face',
    keywords: ['hugging face', 'publish', 'write token', 'private repository', 'hf token', 'export'],
    guide: { chapter: 'using-the-app', anchor: 'publish-a-dataset-to-hugging-face' },
    app: { route: '/datasets?section=export' } },
    { id: 'hf-publish-token', kind: 'setting', title: 'Hugging Face publishing token',
      keywords: ['hugging face', 'publish', 'write permission', 'HF_TOKEN', 'dataset repository'],
      guide: { chapter: 'using-the-app', anchor: 'publish-a-dataset-to-hugging-face' },
      app: { route: '/plugins/hf_publish/settings', focus: 'HF_TOKEN' } }],
  whatsNew: [{
    id: '2026-09-09-hf-style-dataset-card',
    date: '2026-09-09',
    title: 'Prepare Hugging Face publishing and export accurate Style cards',
    blurb: 'The Hugging Face dataset card now explains that Style LoRAs are '
      + 'always-on and use content-only captions. It no longer presents the '
      + 'internal dataset identifier as a trigger. Character and Concept '
      + 'dataset cards keep their trigger instructions. Import & export now '
      + 'links to this plugin’s settings when the publishing token is missing; '
      + 'missing-token errors point to the same settings.',
    to: '/datasets?section=export',
  }],
  paritySkip: [],
}
