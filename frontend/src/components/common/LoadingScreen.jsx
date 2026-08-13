/**
 * Full-screen loading state for lazy-loaded chunks (routes, heavy workspaces).
 * Gives a clear, obviously-alive "it's working" signal on slow links instead of
 * a blank or frozen screen while a chunk downloads, parses and mounts.
 *
 * The spinner is GPU-composited and the indeterminate bar sweeps on its own, so
 * even while the main thread is busy parsing a large bundle the user can see the
 * app is doing something.
 */
export default function LoadingScreen({ label = 'Loading…' }) {
  return (
    <div className="flex h-svh w-full flex-col items-center justify-center gap-5 bg-zinc-950 px-6"
         role="status" aria-live="polite">
      <div className="h-11 w-11 animate-spin rounded-full border-4 border-zinc-800 border-t-indigo-400"
           style={{ willChange: 'transform', transform: 'translateZ(0)' }}
           aria-hidden="true" />
      <div className="boot-indeterminate w-full max-w-xs" aria-hidden="true" />
      <p className="text-sm text-zinc-400">{label}</p>
    </div>
  )
}
