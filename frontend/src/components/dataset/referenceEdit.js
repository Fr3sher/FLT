/* Reference-photo editing: which engines can edit, what the default pick is, and
   the small guards the modal relies on. PURE JS (no JSX) so node --test can
   import and exercise it directly — same split as engineSelection.js.

   The ✦ Edit modal sends the reference + a prompt to an API engine and gets an
   edited candidate back. Klein is deliberately out of scope for editing (it is
   the local GPU engine), so the edit engine set is NOT the generation engine
   set — it is the API subset. */
import { primaryEngine, readEngines, API_ENGINES, ENGINE_LABELS } from './engineSelection.js';

/** Engines that can edit the reference — DERIVED from API_ENGINES, never a second
 *  hardcoded list. The server accepts exactly svc.API_ENGINES on /ref/edit, and a
 *  private copy here is how the modal ends up offering what the route refuses (or,
 *  as happened with OpenRouter, hiding what the route would have accepted). Klein
 *  is excluded for free: it has never been an API engine. Copied, not aliased, so
 *  a caller can't mutate the generation list through this one.
 *  Order = canonical engine order = toggle order in the modal. */
export const EDIT_ENGINES = [...API_ENGINES];

/** The refusal shown for a non-editable engine, DERIVED from EDIT_ENGINES:
 *  "Pick Nano Banana Pro, ChatGPT or OpenRouter". The old sentence named two
 *  engines and kept naming two after a third became editable — a hardcoded list
 *  inside a message rots exactly like a hardcoded list anywhere else. */
export function editEngineNames() {
  const names = EDIT_ENGINES.map((e) => ENGINE_LABELS[e] || e);
  if (!names.length) return '';
  const last = names[names.length - 1];
  const head = names.slice(0, -1);
  return head.length ? `${head.join(', ')} or ${last}` : last;
}

export function editEngineChoiceMessage() {
  const names = editEngineNames();
  return names ? `Pick ${names}` : 'No image engine can edit the reference';
}

/** The engine the modal opens on: the workspace's PRIMARY generation engine when
 *  it can also edit, else ChatGPT. So a profile generating with Nano Banana edits
 *  with Nano Banana; one generating with Klein (can't edit) falls back to ChatGPT
 *  rather than a dead selection. */
export function defaultEditEngine(storage) {
  const primary = primaryEngine(readEngines(storage));
  return EDIT_ENGINES.includes(primary) ? primary : 'chatgpt';
}

/** Why the "Generate edit" button is disabled, or null when it can run. An empty
 *  prompt is the only hard block: the edit is free-form, but it needs SOMETHING. */
export function editBlockedReason(prompt, engine) {
  if (!EDIT_ENGINES.includes(engine)) return editEngineChoiceMessage();
  if (!prompt || !prompt.trim()) return 'Describe the edit first';
  return null;
}

/** The modal's phase, DERIVED from the server's `reference_edit` payload object
 *  (not local state) so it restores correctly after a tab sleep or reload:
 *  'idle' (no pending edit / form), 'running', 'ready' (Before/After), 'failed'. */
export function editPhase(referenceEdit) {
  const s = referenceEdit?.status;
  return (s === 'running' || s === 'ready' || s === 'failed') ? s : 'idle';
}

/** Advisory shown when a generation batch is live. A Keep is provably safe (the
 *  batch snapshotted the reference at launch), so this INFORMS, it does not block:
 *  the point is that editing changes only FUTURE batches. Returns null when no
 *  batch is running. `activity` is the live dataset-activity object (or null). */
export function batchLiveNote(activity) {
  return activity && activity.kind === 'generate'
    ? "A batch is running. Editing the reference won't change variations already "
      + 'generated or still in flight — only future batches use the edited photo.'
    : null;
}

// Re-exported so the modal imports one module for all edit constants.
export { API_ENGINES, ENGINE_LABELS };
