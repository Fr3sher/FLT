import { GUIDE } from './guide.js'
import { HELP } from './help.js'
import { WHATS_NEW } from './whatsNew.js'

export default {
  id: 'resource_monitor',
  guide: GUIDE,
  help: HELP,
  whatsNew: WHATS_NEW,
  nav: [], routes: [], hosts: [],
  slots: {
    'resource_monitor.readout': [
      { id: 'machine-readout', panel: () => import('./components/Readout.jsx') },
    ],
  },
}
