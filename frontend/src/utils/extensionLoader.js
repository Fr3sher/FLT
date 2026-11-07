// Deprecated one-cycle alias for callers of the old manifest. App boot uses
// loadPlugins only; this adapter shares its script cache and never mounts twice.
import { mountModuleScript } from '../plugins/moduleScripts.js'

export function mountExtensionScripts(list, doc = document) {
  const mounted = []
  for (const ext of list || []) {
    if (!ext || !ext.frontend_entry) continue
    const { created } = mountModuleScript(ext.frontend_entry, doc, { extension: ext.name })
    if (created) mounted.push(ext.name)
  }
  return mounted
}

export async function loadExtensions(doc = document) {
  try {
    const res = await fetch('/api/extensions/')
    if (!res.ok) return []
    const data = await res.json()
    return mountExtensionScripts(data.extensions, doc)
  } catch (err) {
    console.warn('extensions manifest unavailable:', err)
    return []
  }
}
