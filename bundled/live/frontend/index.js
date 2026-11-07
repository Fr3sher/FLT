import { GUIDE } from './guide.js'
import { VIDEO_LANE_TOPICS } from './help.js'
import { WHATS_NEW } from './whatsNew.js'
import { labels, setupRows, catalog } from './setup.js'

export default {
  id: 'live', guide: GUIDE, nav: [], routes: [], hosts: [],
  slots: {
    'studio.tab': [{ id: 'live', label: 'Live', icon: 'radio', badge: 'beta',
      panel: () => import('./studio/live/LiveStudio.jsx') }],
    'setup.card': [{ id: 'live', panel: () => import('./LiveInstallCard.jsx') }],
    'setup.step': [{ id: 'live', labels, rows: setupRows, catalog }],
  },
  help: VIDEO_LANE_TOPICS, whatsNew: WHATS_NEW, paritySkip: [],
}
