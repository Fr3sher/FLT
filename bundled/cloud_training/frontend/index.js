import { GUIDE, guideHelp } from './guide.js';
import { cloudContinueLane } from './dataset/cloudTraining.js';
import { cloudSettingsSlots } from './settings/contributions.js';
import { CLOUD_HELP_TOPICS } from './help/cloud.js';
import { CLOUD_WHATS_NEW } from './whatsNew.js';

export default {
  guide: GUIDE,
  id: 'cloud_training', nav: [], routes: [], hosts: [],
  help: CLOUD_HELP_TOPICS.map(guideHelp), whatsNew: CLOUD_WHATS_NEW, paritySkip: [],
  slots: {
    ...cloudSettingsSlots,
    'runs.hub': [{ id: 'cloud-runs', panel: () => import('./CloudRunsHub.jsx') }],
    'training.launch': [{ id: 'cloud-launch', panels: {
      dataset: () => import('./dataset/DatasetCloudTraining.jsx'),
      video: () => import('./video/VideoCloudTraining.jsx'),
    } }],
    'training.continue.lane': [cloudContinueLane],
    'training.dense': [{ id: 'full-model', panel: () => import('./dataset/DenseTraining.jsx') }],
  },
};
