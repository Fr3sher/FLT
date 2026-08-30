import { useEffect, useState } from 'react'
import { quicStatusFromEntries } from '../../utils/quicStatus'

/** ⚡ A tiny, honest transport badge for the header: a lightning bolt that
 * turns green (and earns the "QUIC" label) the moment the browser is talking
 * to this app over HTTP/3.
 *
 * WHY THE PERFORMANCE API, NOT THE SERVER: the app can be served through any
 * mix of waitress, a Docker reverse proxy, or a CDN — the browser is the only
 * place that knows which protocol the ACTIVE connection used. The negotiated
 * protocol is exposed per resource via PerformanceResourceTiming, so the badge
 * simply reads the truth the browser already measured.
 *
 * The badge is deliberately colour-plus-label: the bolt alone turns green, and
 * the word "QUIC" appears alongside it — a green-only indicator would be
 * invisible to a colour-blind user, and a persistent "QUIC" chip with nothing
 * behind it would be noise on the millions of HTTP/1.1 installs. */
function readStatus() {
  if (typeof performance === 'undefined' || typeof performance.getEntriesByType !== 'function') {
    return { active: false, protocol: null }
  }
  const entries = [
    ...(performance.getEntriesByType('navigation') || []),
    ...(performance.getEntriesByType('resource') || []),
  ]
  return quicStatusFromEntries(entries, { origin: window.location.origin })
}

export default function QuicIndicator() {
  const [status, setStatus] = useState(() => readStatus())

  useEffect(() => {
    let alive = true
    const refresh = () => { if (alive) setStatus(readStatus()) }

    // New resource entries are the only realistic path to QUIC becoming true
    // after the page loads (the navigation entry is fixed at load time). Watch
    // for them when the browser supports it…
    if (typeof PerformanceObserver !== 'undefined') {
      let observer
      try {
        observer = new PerformanceObserver(() => { refresh() })
        observer.observe({ entryTypes: ['resource'] })
      } catch {
        // …otherwise fall back to a light poll that still catches late entries.
        const t = setInterval(refresh, 5000)
        return () => { alive = false; clearInterval(t) }
      }
      return () => { alive = false; observer.disconnect() }
    }

    const t = setInterval(refresh, 5000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const active = status.active
  return (
    <span
      title={active
        ? 'Connected over QUIC (HTTP/3) — the fast lane'
        : 'Not connected over QUIC'}
      aria-label={active ? 'Connected over QUIC' : 'Not connected over QUIC'}
      className={`inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[0.5625rem] font-semibold uppercase tracking-wide leading-none transition-colors ${
        active
          ? 'border border-emerald-400/40 bg-emerald-500/10 text-emerald-300'
          : 'text-content-subtle hover:text-content-muted'
      }`}
    >
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"
        className={`h-3 w-3 ${active ? 'text-emerald-400' : 'text-current'}`}>
        <path d="M13 2 4.5 13.5H11L9.5 22 19 9.5h-6.5L13 2Z" />
      </svg>
      {active && <span>QUIC</span>}
    </span>
  )
}
