import { guideChapters } from '../plugins/registry.js'
import { sliceGuideSection } from '../utils/guideSection.js'

const CHAPTER_LOADERS = {
  'getting-started': () => import('../../../docs/guide/getting-started.md?raw'),
  'using-the-app': () => import('../../../docs/guide/using-the-app.md?raw'),
  'dataset-guide': () => import('../../../docs/DATASET_GUIDE.md?raw'),
  'settings-reference': () => import('../../../docs/guide/settings-reference.md?raw'),
  'troubleshooting': () => import('../../../docs/guide/troubleshooting.md?raw'),
  'getting-help': () => import('../../../docs/guide/getting-help.md?raw'),
}

/** The modal and guide read the same active archive content. No fallback chapter. */
export async function loadGuideSection(topic) {
  const id = topic?.guide?.chapter
  if (!id) return ''
  const mod = await CHAPTER_LOADERS[id]?.()
  const chapter = guideChapters(mod ? [{ id, source: mod.default }] : []).find(item => item.id === id)
  return sliceGuideSection(chapter?.source || '', topic.guide.anchor)
}
