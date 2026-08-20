import { useEffect, useRef } from 'react'

/**
 * Full-screen loading state for lazy-loaded chunks (routes, heavy workspaces).
 * Gives a clear, obviously-alive "it's working" signal on slow links instead of
 * a blank or frozen screen while a chunk downloads, parses and mounts.
 *
 * The spinner is driven with requestAnimationFrame so it turns even under
 * prefers-reduced-motion or if CSS animations are disabled, and the
 * indeterminate bar sweeps on its own — so even while the main thread is busy
 * parsing a large bundle the user can see the app is doing something.
 */
export default function LoadingScreen({ label = 'Loading…' }) {
  const spinner = useRef(null)

  useEffect(() => {
    const el = spinner.current
    if (!el) return
    let raf = 0
    let t0 = null
    const spin = (t) => {
      if (t0 === null) t0 = t
      el.style.transform = 'rotate(' + (((t - t0) * 0.36) % 360) + 'deg)'
      raf = requestAnimationFrame(spin)
    }
    raf = requestAnimationFrame(spin)
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <div className="flex h-svh w-full flex-col items-center justify-center gap-5 bg-zinc-950 px-6"
         role="status" aria-live="polite">
      <div ref={spinner}
        className="h-12 w-12 rounded-full border-4 border-zinc-800 border-t-indigo-400 border-r-indigo-600"
        aria-hidden="true" />
      <div className="boot-indeterminate w-full max-w-xs" aria-hidden="true" />
      <p className="text-sm text-zinc-400">{label}</p>
    </div>
  )
}
