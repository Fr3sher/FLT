import { GUIDE } from './guide.js';
import { CANVAS_HELP } from './help.js';
import { WHATS_NEW } from './whatsNew.js';

export default {
  id: 'canvas',
  nav: [{ to: '/canvas', label: '◉ Canvas' }],
  routes: [{ path: '/canvas', page: () => import('./pages/CanvasPage.jsx') }],
  hosts: [], slots: {}, paritySkip: [], guide: GUIDE,
  help: CANVAS_HELP, whatsNew: WHATS_NEW,
};
