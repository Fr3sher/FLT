/**
 * ⚡ The one place that knows whether the browser is talking to this server
 * over QUIC (HTTP/3).
 *
 * The browser exposes the negotiated protocol of every same-origin resource as
 * `PerformanceResourceTiming.nextHopProtocol` (and the initial navigation as
 * `PerformanceNavigationTiming.nextHopProtocol`). When the value starts with
 * `h3` the connection really is QUIC — anything else (http/1.1, h2) is not.
 * This is deliberately framework-free so `node --test` can cover it without a
 * DOM.
 */

/** Any protocol string that starts with this is HTTP/3/QUIC. */
export const QUIC_PROTOCOL_PREFIX = 'h3';

/** True when a `nextHopProtocol` value means the connection ran over QUIC. */
export function isQuicProtocol(protocol) {
  return typeof protocol === 'string'
    && protocol.trim().toLowerCase().startsWith(QUIC_PROTOCOL_PREFIX);
}

function sameOrigin(entry, origin) {
  try {
    const u = new URL(entry?.name, origin);
    return u.origin === origin;
  } catch {
    return false;
  }
}

/**
 * Scan performance entries for a QUIC connection to `origin`.
 *
 * @param {Array<{name?:string, nextHopProtocol?:string}>} entries
 * @param {{origin?:string}} [opts] — pass the app origin to ignore CDNs and
 *   third-party hosts; a relative entry name is resolved against it.
 * @returns {{active:boolean, protocol:string|null}} `active` is true when at
 *   least one same-origin resource (or the navigation) used HTTP/3. `protocol`
 *   is the first matching protocol found, or the first plain protocol when no
 *   QUIC entry exists, or null when nothing was measured yet.
 */
export function quicStatusFromEntries(entries, { origin = null } = {}) {
  const list = Array.isArray(entries) ? entries : [];
  for (const entry of list) {
    const protocol = entry?.nextHopProtocol;
    if (!isQuicProtocol(protocol)) continue;
    if (origin && !sameOrigin(entry, origin)) continue;
    return { active: true, protocol };
  }
  const fallback = list.find((entry) => typeof entry?.nextHopProtocol === 'string')?.nextHopProtocol || null;
  return { active: false, protocol: fallback };
}
