import { GUIDE } from './guide.js'
import { HELP } from './help.js'
import { NEWS } from './whatsNew.js'
import { SEEDVR2_ENGINE } from './lib/engine.js'
import { setupRows, catalog } from './lib/setup.js'
export default {
  id: 'seedvr2', guide: GUIDE, nav: [], routes: [], hosts: [],
  slots: {
    'improve.engine': [SEEDVR2_ENGINE],
    'setup.card': [{ id: 'seedvr2', panel: () => import('./panels/SeedVr2InstallCard.jsx') }],
    'setup.step': [{ id: 'seedvr2', rows: setupRows, catalog }],
    'settings.group': [{ id: 'seedvr2', section: 'engines', after: 'lora-presets',
      title: 'SeedVR2', blurb: 'Faithful image restoration, model preparation, tiling and finishing.',
      keywords: ['seedvr2', 'restore', 'upscale', 'tiling', 'super resolution'],
      panel: () => import('./panels/SeedSettings.jsx') }],
  },
  help: HELP, whatsNew: NEWS, paritySkip: [],
}
