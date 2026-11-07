import { GUIDE } from './guide.js'
import { HELP } from './help.js'
import { NEWS } from './whatsNew.js'
import { KLEIN_ENGINE } from './lib/engine.js'
export default {
  id: 'image_upscale', guide: GUIDE, nav: [], routes: [], hosts: [],
  slots: {
    'improve.engine': [KLEIN_ENGINE],
    'improve.editor': [{ id: 'klein', panel: () => import('./panels/KleinImproveNote.jsx') }],
    'settings.group': [{ id: 'image-upscale', section: 'engines', after: 'lora-presets',
      title: 'Klein Improve', blurb: 'Improve detail with Klein, its instruction, LoRA controls and finishing.',
      keywords: ['klein', 'improve', 'detail', 'instruction', 'finishing'],
      panel: () => import('./panels/ImproveSettings.jsx') }],
  },
  help: HELP, whatsNew: NEWS, paritySkip: [],
}
