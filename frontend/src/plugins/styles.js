// Styles are part of the same boot as the module, and must be ready before a
// descriptor can mount a panel. A failed load never leaves a cached success.
const documents = new WeakMap()

export async function loadPluginStyles(urls, timeoutMs, doc) {
  if (!Array.isArray(urls) || urls.some((url) => typeof url !== 'string')) {
    return { ok: false, why: 'list is invalid' }
  }
  let entries = documents.get(doc)
  if (!entries) { entries = new Map(); documents.set(doc, entries) }
  const loaded = []
  const remove = () => {
    for (const url of loaded) {
      entries.get(url)?.element?.remove?.()
      entries.delete(url)
    }
  }
  for (const url of urls) {
    if (!entries.has(url)) {
      const entry = {}
      const completion = new Promise((resolve) => {
        let done = false
        const finish = (result) => {
          if (done) return
          done = true
          clearTimeout(timer)
          if (!result.ok) { entry.element?.remove?.(); entries.delete(url) }
          resolve(result)
        }
        const timer = setTimeout(() => finish({ ok: false, why: `timed out after ${timeoutMs} ms` }), timeoutMs)
        try {
          const element = doc.createElement('link')
          entry.element = element
          element.rel = 'stylesheet'
          element.href = url
          element.onload = () => finish({ ok: true })
          element.onerror = () => finish({ ok: false, why: 'failed to load' })
          doc.head.appendChild(element)
        } catch { finish({ ok: false, why: 'failed to mount' }) }
      })
      entry.completion = completion
      entries.set(url, entry)
    }
    const result = await entries.get(url).completion
    if (!result.ok) { entries.delete(url); remove(); return result }
    loaded.push(url)
  }
  return { ok: true, remove }
}
