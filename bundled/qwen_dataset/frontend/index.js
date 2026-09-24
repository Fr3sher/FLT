import { QWEN_ENGINE, modelPreparationRows, setupRows } from './lib/engine.js'
import { GUIDE } from './guide.js'

const topic = (id, title, focus, keywords, kind = 'setting') => ({
  id, title, kind, keywords: ['qwen', 'dataset forge', ...keywords],
  guide: { chapter: 'settings-reference', anchor: 'dataset-forge-qwen-image-2-1' },
  app: { route: '/plugins/qwen_dataset/settings', focus },
})

export default {
  id: 'qwen_dataset', guide: GUIDE, nav: [], routes: [], hosts: [], paritySkip: [],
  slots: {
    'engine.spec': [QWEN_ENGINE],
    'settings.group': [{ id: 'qwen-dataset', section: 'engines',
      title: 'Dataset Forge', blurb: 'Prepare Qwen-Image 2.1 and tune local dataset generation.',
      keywords: ['qwen', 'dataset forge', 'reference', 'sampling', 'cfg'],
      panel: () => import('./panels/QwenSettings.jsx') }],
    'setup.card': [{ id: 'qwen-dataset', panel: () => import('./panels/QwenPreparation.jsx') }],
    'setup.step': [{ id: 'qwen-dataset', rows: setupRows, catalog: modelPreparationRows }],
  },
  help: [
    topic('qwen-dataset-prepare', 'Prepare Qwen-Image 2.1', 'qwen-dataset-preparation', ['install', 'models', 'comfyui'], 'action'),
    topic('qwen-dataset-steps', 'Qwen sampling steps', 'qwen-dataset-steps', ['steps', 'sampling']),
    topic('qwen-dataset-cfg', 'Qwen prompt guidance', 'qwen-dataset-cfg', ['cfg', 'guidance']),
    topic('qwen-dataset-sampler', 'Qwen sampler', 'qwen-dataset-sampler', ['sampler', 'sampling']),
    topic('qwen-dataset-scheduler', 'Qwen scheduler', 'qwen-dataset-scheduler', ['scheduler', 'sampling']),
    topic('qwen-dataset-reference-resolution', 'Qwen reference resolution', 'qwen-dataset-reference-resolution', ['reference', 'resolution', 'memory']),
    topic('qwen-dataset-negative-prompt', 'Qwen negative prompt', 'qwen-dataset-negative-prompt', ['negative prompt']),
    topic('qwen-dataset-unet', 'Qwen model filename', 'qwen-dataset-unet', ['model', 'filename']),
    topic('qwen-dataset-text-encoder', 'Qwen text encoder filename', 'qwen-dataset-text-encoder', ['text encoder', 'filename']),
    topic('qwen-dataset-vae', 'Qwen VAE filename', 'qwen-dataset-vae', ['vae', 'filename']),
  ],
  whatsNew: [{ id: '2026-09-23-qwen-dataset-forge', date: '2026-09-23',
    title: 'Generate dataset variations locally with Qwen-Image 2.1',
    blurb: 'Dataset Forge adds a Qwen-Image 2.1 engine to Generate variations. Use your existing shot cards and reference photos, then curate and retry results in the same grid. Plugin settings prepare its model files and expose sampling and reference controls. Inspired by Jolanoff and acekiube’s dataset workflows; Qwen model weights use a non-commercial research licence.',
  }],
}
