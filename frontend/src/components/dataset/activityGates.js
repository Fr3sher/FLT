import { laneOf } from '../../utils/activityLanes.js';

// Adding images never conflicts with work that is merely QUEUED (a generation
// batch, an ✨ improve batch, a reference edit): those hold a place in the
// serialized image queue, not the dataset's rows, and an improve batch works off
// the selection it captured when it started, so a freshly imported image cannot
// join it half-way. A pass that rewrites rows — captioning, watermarks, an
// export — still blocks, as it always did. `laneOf` owns that split; this used
// to name 'generate' by hand, which is why an improve batch closed the dropzone.
export function isDatasetImportBlocked({ localBusy, activity }) {
  return !!localBusy || (!!activity?.kind && laneOf(activity.kind) !== 'queue');
}

// Activities the ⏹ Stop generation button EXISTS to end. They must never disable
// it: the activity registry publishes 'generate' for the whole batch (every
// engine — Klein, Nano Banana, ChatGPT), which makes `busy` true for exactly as
// long as the user needs Stop. Any OTHER activity (captioning, watermarks…) still
// blocks, so this stays a targeted exemption and not a blanket unlock.
const STOPPABLE_ACTIVITY_KINDS = ['generate', 'improve'];

export function isStopGenerationBlocked({ busy, activity, cancelling }) {
  if (cancelling) return true;   // a stop is already on its way — no double-click
  return !!busy && !STOPPABLE_ACTIVITY_KINDS.includes(activity?.kind);
}
