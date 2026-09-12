import { engineIds } from '../../engines/catalog.js'
import { BarChart3, Dumbbell, Globe, Monitor, Palette, PenLine, Save, Search, Wrench } from 'lucide-react';
// Data-driven section list for the Settings page: sidebar labels, deep-link
// ids, the mono eyebrow tag, and the keywords the sidebar search matches on.

export const SETTINGS_SECTIONS = [
  { id: 'overview', title: 'Overview', icon: BarChart3, eyebrow: 'status',
    description: 'What is configured and what to do next.',
    keywords: ['status', 'summary', 'capabilities', 'ready'] },
  { id: 'engines', title: 'Image engines', icon: Palette, eyebrow: 'generation',
    description: 'Local image engines and shared generation defaults.',
    // The API engines' own words (their providers' names) come from their
    // plugin's settings group (sectionKeywords below), not from here.
    keywords: ['klein', 'krea', 'krea 2 edit',
      'grounding', 'engine',
      'lora', 'preset', 'texture', 'anatomy', 'nsfw', 'identity', 'prompt', 'guard',
      'hi-res fix', 'hires fix', 'highres', 'second pass', 'two pass', '2 pass', 'latent upscale',
      'detail', 'denoise'] },
  { id: 'scraping', title: 'Shared service access', icon: Search, eyebrow: 'services',
    description: 'Access shared by the Civitai browser, model downloads and installed plugins.',
    keywords: ['civitai', 'api key', 'nsfw', 'source', 'import'] },
  { id: 'local-tools', title: 'Local tools', icon: Monitor, eyebrow: 'integrations',
    description: 'ComfyUI, Ollama and ai-toolkit — where they run and where they live.',
    keywords: ['comfyui', 'ollama', 'ai-toolkit', 'vision model', 'path', 'url', 'hugging face', 'hf token', 'directory', 'install'] },
  { id: 'captioning', title: 'Captioning & quality', icon: PenLine, eyebrow: 'pipeline',
    description: 'How captions are written and how face similarity is judged.',
    keywords: ['caption', 'joycaption', 'backend', 'face score', 'threshold', 'green', 'orange', 'similarity',
      'import', 'resolution', 'downscale', 'normalize', '1024', 'webp', 'lossless', 'original size'] },
  { id: 'training', title: 'Training', icon: Dumbbell, eyebrow: 'training',
    description: 'Default model family and training settings.',
    keywords: ['family', 'zimage', 'sdxl', 'krea', 'gpu'] },
  { id: 'storage', title: 'Storage', icon: Save, eyebrow: 'disk',
    description: 'Where everything lives on disk, and how much space it takes.',
    keywords: ['storage', 'disk', 'space', 'full', 'drive', 'path', 'folder', 'location',
      'move', 'relocate', 'another drive', 'data', 'dataset root', 'checkpoint store',
      'trash', 'archive',
      'free space', 'gb', 'cleanup', 'orphan'] },
  { id: 'server', title: 'Server & access', icon: Globe, eyebrow: 'network',
    description: 'Port, LAN access and the access token.',
    keywords: ['port', 'host', 'lan', 'network', 'token', 'remote', 'phone', 'bind'] },
  { id: 'maintenance', title: 'Maintenance', icon: Wrench, eyebrow: 'housekeeping',
    description: 'Updates, server log and bug reports.',
    keywords: ['update', 'restart', 'log', 'diagnostic', 'version', 'bug'] },
]

/* Sidebar LED per section — derived from live capabilities so the rail doubles
   as a health map of the rig: 'ready' | 'partial' | 'off' | null (no LED). */
export function sectionStatus(id, caps) {
  const c = caps || {}
  const e = c.engines || {}
  switch (id) {
    case 'engines':
      return engineIds().some((id) => e[id]) ? 'ready' : 'off'
    case 'local-tools': {
      const parts = [
        !!(c.comfyui && c.comfyui.reachable),
        // The ACTIVE provider's reachability. Keyed on Ollama alone, this LED
        // read "off" on a perfectly healthy LM Studio install.
        (((c.local_llm && c.local_llm.provider) || 'ollama') === 'lmstudio'
          ? !!(c.lmstudio && c.lmstudio.reachable)
          : !!(c.ollama && c.ollama.reachable)),
        !!(c.aitoolkit && c.aitoolkit.valid),
      ]
      const n = parts.filter(Boolean).length
      return n === 3 ? 'ready' : n > 0 ? 'partial' : 'off'
    }
    case 'captioning': {
      const cap = c.captioners || {}
      // The active provider, falling back to the old expression for an older
      // caps payload: a healthy LM Studio install lit this LED off.
      return (cap.joycaption
        || (cap.local_llm !== undefined ? cap.local_llm : cap.ollama)) ? 'ready' : 'off'
    }
    case 'training':
      return c.training_visible ? 'ready' : 'off'
    default:
      return null
  }
}

/** General Settings indexes core sections; product fields live in their plugin. */
export function sectionKeywords(section) {
  return section.keywords
}

export function matchesQuery(section, q) {
  const needle = (q || '').trim().toLowerCase()
  if (!needle) return true
  return section.title.toLowerCase().includes(needle)
    || sectionKeywords(section).some((k) => k.includes(needle))
}
