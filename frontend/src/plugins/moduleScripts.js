// One module element per URL/document, shared with the old extension alias.
// Keeping its completion promise also lets a concurrent caller await the same
// script instead of mounting React before a pending entry has registered.
const documents = new WeakMap()

export function mountModuleScript(url, doc, attributes = {}) {
  let entries = documents.get(doc)
  if (!entries) { entries = new Map(); documents.set(doc, entries) }
  const key = doc.baseURI ? new URL(url, doc.baseURI).href : url
  const existing = entries.get(key)
  if (existing) return { ...existing, created: false }
  const element = doc.createElement('script')
  element.type = 'module'
  element.src = url
  Object.assign(element.dataset, attributes)
  let finish
  const completion = new Promise((resolve) => { finish = resolve })
  element.onload = () => finish({ ok: true })
  element.onerror = () => finish({ ok: false, why: 'failed to load' })
  const entry = { element, completion }
  entries.set(key, entry)
  try {
    doc.head.appendChild(element)
  } catch {
    finish({ ok: false, why: 'failed to mount' })
  }
  return { ...entry, created: true }
}

export async function loadModuleScript(url, timeoutMs, doc) {
  let timer
  try {
    const { completion } = mountModuleScript(url, doc)
    return await Promise.race([
      completion,
      new Promise((resolve) => {
        timer = setTimeout(() => resolve({ ok: false, why: `timed out after ${timeoutMs} ms` }), timeoutMs)
      }),
    ])
  } catch {
    return { ok: false, why: 'failed to mount' }
  } finally {
    clearTimeout(timer)
  }
}
