// Opt-in SDK fixture: use the application's service graph and context identities.
// The JSX loader must run before importing the host's component services.
import './mountJsx.mjs'

const { configureHostRuntime } = await import('../../src/plugins/runtimeHost.jsx')
const { publishRuntime } = await import('../../src/plugins/loadPlugins.js')
const { resetRegistry, setEnabled } = await import('../../src/plugins/registry.js')

export function installRuntimeHost(t) {
  const saved = Object.fromEntries(['window', 'document', 'fetch'].map(name =>
    [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  t.after(() => {
    resetRegistry()
    setEnabled([])
    for (const [name, descriptor] of Object.entries(saved)) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
  })
  globalThis.window = {}
  globalThis.document = { cookie: '', querySelector: () => null }
  globalThis.fetch = () => { throw new Error('Unexpected request in a runtime host fixture') }
  resetRegistry()
  setEnabled([])
  configureHostRuntime()
  return publishRuntime()
}
