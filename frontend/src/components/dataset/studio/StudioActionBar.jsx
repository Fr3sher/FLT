// react-frontend/src/components/dataset/studio/StudioActionBar.jsx
/**
 * StudioActionBar is FIXED at the bottom of Test Studio. Requested on 2026-07-03: keep Run the
 * test ALWAYS visible, duplicating the setup button, and link directly to option groups. Shortcuts
 * emit studio:reveal to open collapsed StudioSections before scrolling to their anchors;
 * scrollIntoView also scrolls the desktop aside. PAGES_WITH_BOTTOM_BAR includes /studio to raise
 * GlobalJobsDock above it. Optional note, added 2026-08-31, explains a disabled button on its
 * left, used by video for missing start frames; absent means unchanged behavior. Optional
 * runningLabel, added 2026-09-02, shows progress such as Queueing 2 of 3 during video batches;
 * absent preserves the ellipsis.
 */

export default function StudioActionBar({ shortcuts = [], canRun, running, onRun, runLabel = '🚀 Run the test', note = null, runningLabel = null }) {
  const jump = (id) => {
    try { window.dispatchEvent(new CustomEvent('studio:reveal', { detail: id })); } catch { /* ignore */ }
    // Let the section open through setState before scrolling to it.
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };
  return (
    <nav aria-label="Studio quick navigation" data-probe-chrome="action-bar"
      className="fixed bottom-0 left-0 right-0 z-[9960] border-t border-border bg-app/90 backdrop-blur-md">
      <div className="flex items-center gap-1.5 px-3 sm:px-5 py-2 overflow-x-auto">
        {shortcuts.map((s) => (
          <button key={s.id} type="button" onClick={() => jump(s.id)}
            // min-h-10 below lg: a 27-px chip is under the ~40 px a fingertip lands on,
            // and a miss goes to whatever sits behind it (the results grid). Measured by
            // the responsive probe; compact again from lg, where a pointer is precise.
            className="min-h-10 lg:min-h-0 shrink-0 px-2.5 py-1 rounded-full border border-border bg-surface text-content-muted hover:text-content hover:bg-surface-raised text-[0.6875rem] font-medium transition-colors">
            <span aria-hidden="true">{s.emoji}</span> {s.label}
          </button>
        ))}
        {note && (
          <span className="ml-auto min-w-0 shrink truncate text-[0.6875rem] text-content-subtle" title={note}>
            {note}
          </span>
        )}
        <button type="button" onClick={onRun} disabled={!canRun}
          className={`min-h-10 lg:min-h-0 ${note ? '' : 'ml-auto'} shrink-0 px-4 py-1.5 rounded-lg bg-gradient-primary text-gray-950 text-sm font-semibold disabled:opacity-40`}>
          {running ? (runningLabel || '…') : runLabel}
        </button>
      </div>
    </nav>
  );
}
