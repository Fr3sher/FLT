// Explicit development entry. Never import this module in the Store profile.
// Bundled plugin descriptors, collected at BUILD time. `@bundled` is a Vite
// alias for the repository's `bundled/` directory (vite.config.js); the glob
// keys are paths relative to the frontend root, so descriptors are indexed by
// their `id`, never by path. Vite-only on purpose: node --test never imports
// this file (registry.js stays pure).
import { registerDescriptor } from './registry.js'

const modules = import.meta.glob('@bundled/*/frontend/index.js', { eager: true })
const manifests = import.meta.glob('@bundled/*/plugin.json', { eager: true, import: 'default' })

export function registerBundledPlugins() {
  const ids = []
  for (const path of Object.keys(modules).sort()) {
    const descriptor = modules[path] && modules[path].default
    const manifest = Object.values(manifests).find(item => item.id === descriptor?.id)
    const guideOwnership = { chapters: manifest?.guide_ownership?.chapters || [], sections: manifest?.guide_ownership?.sections || [] }
    if (registerDescriptor(descriptor, { external: false, guideOwnership, pluginName: manifest?.name })) ids.push(descriptor.id)
  }
  return ids
}
