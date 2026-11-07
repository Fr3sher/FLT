import { HelpBadge } from '@lds/plugin-sdk';
import { autoIsBusy, autoLimit, autoPhaseLabel } from './videoAutoContinue';

export default function AutoContinuePanel({ session, ready, busy, error, direction, maxClips, referenceMode = false,
  onDirection, onMaxClips, onApply, onStop, onResume }) {
  const active = autoIsBusy(session);
  const valid = autoLimit(maxClips) !== null;
  const changed = session && (direction !== session.direction || Number(maxClips) !== session.max_clips);
  return (
    <section aria-label="Auto continuation" data-testid="auto-continue-panel"
      className="space-y-2 rounded-xl border border-border bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-content">Auto continuation <HelpBadge topic="video-auto-continue" /></h3>
        {session && <span className="text-xs text-content-muted">
          From clip #{session.root_clip_id} · {session.completed} added{session.max_clips ? ` / ${session.max_clips}` : ''}
        </span>}
      </div>
      {session?.lora && (
        <p className="truncate text-xs text-content-muted" title={session.lora} data-testid="auto-continue-lora">
          Character LoRA {String(session.lora).split('/').pop()}
          {Number.isFinite(Number(session.lora_strength)) && session.lora_strength !== null ? ` · ${Number(session.lora_strength).toFixed(2)}` : ''}
          {session.lora_from_clip_id ? ` · kept from clip #${session.lora_from_clip_id}` : ''}
        </p>
      )}
      {session?.panel_lora && (
        <p className="text-xs text-amber-200" data-testid="auto-continue-panel-lora">
          The panel’s {String(session.panel_lora).split('/').pop()} was not used: a take keeps its chain’s LoRA.
          To change character, render one part by hand with the other LoRA, then continue from it.
        </p>
      )}
      <p role="status" className="text-xs text-content-muted">{ready ? autoPhaseLabel(session) : 'Reading Auto status…'}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <label className="block min-w-0 flex-1 text-xs text-content-muted">
          Scene direction (optional)
          <textarea value={direction} onChange={(e) => onDirection(e.target.value)} maxLength={4000} rows={2}
            placeholder="She walks through the garden; the camera follows her."
            className="mt-1 min-h-16 w-full rounded-lg border border-border bg-app p-2 text-sm text-content" />
        </label>
        <label className="block text-xs text-content-muted sm:w-40">
          More clips
          <input type="number" min="0" max="10000" step="1" value={maxClips}
            onChange={(e) => onMaxClips(e.target.value)}
            className="mt-1 min-h-10 w-full rounded-lg border border-border bg-app px-2 text-sm text-content" />
          <span className="mt-1 block">0 = until you stop</span>
        </label>
      </div>
      {!valid && <p role="alert" className="text-xs text-red-300">Enter a whole number from 0 to 10000.</p>}
      <p className="text-xs text-content-muted">
        {referenceMode
          ? 'Auto continuation uses image-to-video clips. Switch to From an image to start a new loop; an existing loop keeps its captured settings and can still be stopped here. '
          : 'Uses the current render settings and the motion model chosen under ⚙. '}
        Each next clip starts from the previous clip’s last frame.
        Auto keeps running if you leave this page. Uncheck Auto to finish the current clip and stop.
      </p>
      {(error || session?.error) && <p role="alert" className="break-words text-xs text-red-300">{error || session.error}</p>}
      <div className="flex flex-wrap gap-2">
        {session && changed && <button type="button" onClick={onApply} disabled={busy || !ready || !valid}
          className="min-h-10 rounded-lg border border-border px-3 text-xs text-content disabled:opacity-40">
          Apply to next clips
        </button>}
        {/* A PAUSED take (a restart, a failed step) is not over: it can Resume,
            and it must be able to END — without this button the only way out
            of a paused session was to start another one from a clip. */}
        {(active || session?.phase === 'paused') && <button type="button" onClick={onStop}
          disabled={busy || (!session.enabled && !session.can_abandon && session.phase !== 'paused')}
          className="min-h-10 rounded-lg border border-border px-3 text-xs text-content disabled:opacity-40">
          Stop Auto
        </button>}
        {session?.phase === 'paused' && session.can_resume !== false && !session.draining && <button type="button" onClick={onResume}
          disabled={busy || !ready || !valid}
          className="min-h-10 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-gray-950 disabled:opacity-40">
          Resume
        </button>}
      </div>
    </section>
  );
}
