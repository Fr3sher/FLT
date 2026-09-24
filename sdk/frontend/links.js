// Project-owned outbound links and disclosure keep one referral configuration.
import { runtime } from './runtime.js'

/** A pure Markdown link token, resolved by the shared guide's one URL builder.
 * Descriptors can therefore be inspected before a browser runtime exists. */
export function vastGuideUrl(path = '/', { tagged = true } = {}) {
  if (typeof path !== 'string' || !/^\/[a-z0-9/-]*$/.test(path)) throw new Error('Use a relative Vast console path.')
  return `lds-guide:vast:${tagged ? 'tagged' : 'plain'}:${path}`
}

export function vastReferralId() { return runtime().links.vastReferralId }
export function vastUrl(...args) { return runtime().links.vastUrl(...args) }
export function vastSignupUrl(...args) { return runtime().links.vastSignupUrl(...args) }
export function VastLink(props) {
  const host = runtime()
  return host.React.createElement(host.links.VastLink, props)
}
export function VastReferralDisclosure(props) {
  const host = runtime()
  return host.React.createElement(host.links.VastReferralDisclosure, props)
}
