import { GUIDE } from './guide.js'
// 🎬 The video lane — the frontend descriptor of the bundled `video` plugin.
// Plain JS on purpose: node --test imports it (the parity, help and slot
// contracts), Vite globs it at build time (src/plugins/bundled.js). The React
// screens are lazy imports, so each is its own chunk and only loads where a
// surface mounts it.
//
// What it contributes:
//   - two ROUTES: `/video-bank` (the Video Bank) and `/video-dataset/:id` (one
//     video training set, worked on) — neither a nav item, on purpose: the lane
//     switch on the bank pages and the datasets list are their doors.
//   - `lanes` (bank / videoBank) — the 🎬 Video tab of the Bank's lane switch.
//   - `studio.tab` — the 🎬 Video tab of the Test Studio.
//   - `datasets.section` — the "Video training sets" list under the image
//     datasets on the Datasets page.
//   - `setup.card` — the Video Test Studio install card.
//   - `setup.step` — the lane's capability rows and install-menu items, so the
//     Setup screen counts the lane and can (re)install its pieces one by one.
//   - the lane's help topics (the Video Bank, datasets and clip Studio).
// No `lucide-react` import here (node resolves a bare package from the
// importing file's folder, and bundled/ has no node_modules): the Studio tabs
// name their icon, the core maps the name.
import { VIDEO_INSTALL_LABELS } from './lib/videoInstallLabels.js'
import { WHATS_NEW } from './whatsNew.js'
import { VIDEO_LANE_TOPICS } from './help/videoLane.js'
import { VIDEO_ML_CARDS, videoInstallCatalog, videoSetupRows } from './lib/videoSetup.js'

export default {
  guide: GUIDE,
  id: 'video',
  nav: [],
  routes: [
    { path: '/video-bank', page: () => import('./pages/VideoBankPage.jsx') },
    { path: '/video-dataset/:id', page: () => import('./pages/VideoDatasetPage.jsx') },
  ],
  slots: {
    'lanes': [
      { id: 'video', panels: {
        bank: () => import('./lanes/VideoLaneTab.jsx'),
        videoBank: () => import('./lanes/VideoLaneTab.jsx'),
      } },
    ],
    'studio.tab': [
      { id: 'video', label: 'Video', icon: 'clapperboard',
        panel: () => import('./studio/video/VideoTestStudio.jsx') },
    ],
    'datasets.section': [
      { id: 'video-datasets', panel: () => import('./videobank/VideoDatasetsPanel.jsx') },
    ],
    'setup.card': [
      { id: 'video-studio', panel: () => import('./setup/VideoStudioInstallCard.jsx') },
    ],
    'setup.step': [
      { id: 'video', labels: VIDEO_INSTALL_LABELS, rows: videoSetupRows, catalog: videoInstallCatalog, mlCards: VIDEO_ML_CARDS },
    ],
  },
  hosts: [],
  help: VIDEO_LANE_TOPICS,
  whatsNew: WHATS_NEW,
  paritySkip: [],
}
