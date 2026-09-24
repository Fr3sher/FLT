// Public services resolve at use time: descriptors and pure helpers can be
// inspected by Node before a browser host exists. Contexts belong to LDS.
export const SDK_VERSION = '1.15.0'

export function runtime() {
  const host = globalThis.window?.lds
  const value = String(host?.sdkVersion || '')
  const version = value.split('.').map(Number)
  if (!host || host.api !== 1 || !/^1\.\d+\.\d+$/.test(value) || version[1] < 7) {
    throw new Error('This plugin requires LDS frontend SDK 1.7 or later in major version 1.')
  }
  return host
}

function service(name, ...args) {
  const fn = runtime()[name]
  if (typeof fn !== 'function') throw new Error(`LDS does not provide the plugin service ${name}.`)
  return fn(...args)
}

export const apiFetch = (...args) => service('apiFetch', ...args)
export const postJson = (...args) => service('postJson', ...args)
// Result-envelope transport: never throws, including HTTP/network failures.
// Existing forms that inspect result.ok must retain this distinct contract.
export const postJsonResult = (...args) => service('postJsonResult', ...args)
export const putJson = (...args) => service('putJson', ...args)
export const patchJson = (...args) => service('patchJson', ...args)
export const del = (...args) => service('del', ...args)
export const postForm = (...args) => service('postForm', ...args)
export const requestHelpTip = (...args) => service('requestHelpTip', ...args)
export const installActionLabel = (...args) => service('installActionLabel', ...args)
export function useToast() { return service('useToast') }
export function HelpBadge(props) {
  const host = runtime()
  return host.React.createElement(host.HelpBadge, props)
}
export function GlobalModelPicker(props) {
  const host = runtime()
  return host.React.createElement(host.GlobalModelPicker, props)
}

export function definePlugin(descriptor) {
  if (!descriptor || typeof descriptor.id !== 'string') throw new Error('A plugin descriptor needs its manifest id.')
  return descriptor
}

export function registerPlugin(descriptor) {
  const accepted = service('registerPlugin', descriptor)
  if (!accepted) throw new Error(`LDS refused the descriptor for ${descriptor?.id || 'this plugin'}.`)
  return descriptor
}
