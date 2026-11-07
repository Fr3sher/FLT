import { GUIDE } from './guide.js'
import { NEURAL_RENDER_TOPICS } from './help.js'
import { WHATS_NEW } from './whatsNew.js'

export default {
  id: 'dlss5',
  nav: [{ to: '/dlss5', label: '✨ DLSS 5' }],
  routes: [{ path: '/dlss5', page: () => import('./Dlss5Page.jsx') }],
  hosts: [], paritySkip: [],
  guide: GUIDE, help: NEURAL_RENDER_TOPICS, whatsNew: WHATS_NEW,
  slots: {
    'settings.group': [{ id: 'dlss5-runtime', section: 'local-tools',
      title: 'DLSS 5 preparation', panel: () => import('./Dlss5Settings.jsx') }],
    'video.neural-render-dialog': [{ id: 'dlss5-dialog',
      panel: () => import('./NeuralRenderDialog.jsx') }],
    'video.neural-compare': [{ id: 'dlss5-compare',
      panel: () => import('./SideBySideVideo.jsx') }],
  },
}
