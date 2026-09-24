/* ⏭ What this launch does with the continuation that is armed — said where the
 * frames are picked, in every mode.
 *
 * Measured on 2026-09-07: a continuation staged from a References clip was
 * armed in the start frame strip alone. References mode does not render that
 * strip (the references panel takes its place), so nothing on screen showed
 * the frame was there, and Generate built its launch from the reference guide
 * alone — a fresh clip, joined to nothing, under a "Queued" toast. The clip
 * was deleted and the take done again.
 *
 * So: a mode that runs the continuation says which clip it lands behind, and a
 * mode that does not says that too, with the two ways out — the mode that
 * would run it, and dropping it. Not a refusal: launching a new clip while one
 * is armed is a legitimate thing to want. Never in silence is the whole rule.
 */
import { MODE_NAMES } from './videoContinuation.js';

export default function VideoContinuationNotice({ state, mode, isReference = false, onMode, onDrop }) {
  const used = state?.used || [];
  const ignored = state?.ignored || [];
  if (!used.length && !ignored.length) return null;
  return (
    <>
      {used.length > 0 && (
        <p className="rounded-lg border border-border bg-surface-raised px-2.5 py-1.5 text-[0.6875rem] text-content-muted">
          {/* Two ⏭ clicks are an ordinary gesture and make two videos, each
              behind its own parent — a sentence written for one join says
              something false about that (verification, 2026-09-07). */}
          ⏭ {used.map((id) => `clip #${id}`).join(', ')}: {used.length > 1
            ? 'each render lands joined behind its own clip — one video per start frame, that clip then the new motion.'
            : 'the render lands joined behind it — one video, that clip then the new motion.'}
          {isReference
            ? ' It runs with the references that clip was made with, starting on its last frame — the first frame guide below.'
            : ' Remove the frame from the strip to launch a plain clip instead.'}
        </p>
      )}
      {ignored.map(({ id, mode: home }) => (
        <p key={id} className="mt-1.5 flex flex-wrap items-center gap-2 rounded-lg border border-amber-400/40 bg-amber-500/10 px-2.5 py-1.5 text-[0.6875rem] text-amber-200">
          ⏭ Clip #{id} is armed to be continued, and {MODE_NAMES[mode] || mode} does not start from it:
          this Generate renders a NEW clip.
          <button type="button" onClick={() => onMode?.(home)}
            className="min-h-10 rounded-md border border-amber-400/40 px-2 py-1 font-semibold hover:bg-amber-500/20 lg:min-h-0">
            Continue it in {MODE_NAMES[home] || home}
          </button>
          <button type="button" onClick={() => onDrop?.(id)}
            className="min-h-10 rounded-md border border-amber-400/40 px-2 py-1 hover:bg-amber-500/20 lg:min-h-0">
            Drop the continuation
          </button>
        </p>
      ))}
    </>
  );
}
