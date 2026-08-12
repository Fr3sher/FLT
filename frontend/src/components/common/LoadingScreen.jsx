/**
 * Full-screen loading state for lazy-loaded chunks (routes, heavy workspaces).
 * Gives a clear "it's working" signal on slow links instead of a blank screen
 * while a chunk downloads, parses and mounts.
 */
export default function LoadingScreen({ label = 'Loading…' }) {
  return (
    <div className="flex h-svh w-full flex-col items-center justify-center gap-4 bg-zinc-950"
         role="status" aria-live="polite">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-zinc-700 border-t-zinc-300"
           aria-hidden="true" />
      <p className="text-sm text-zinc-400">{label}</p>
    </div>
  )
}
