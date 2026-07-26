// Face-similarity gate, UI side (PURE JS, JSX-free so node --test can import it).
//
// The RULE lives on the server (face_dataset_service.face_scoring_block_reason) and
// arrives in the dataset payload as `face_scoring_blocked`: a sentence explaining
// why the pass is refused, or null. Nothing here knows about subject types — this
// module only decides how to PRESENT a reason it is handed. That is deliberate: the
// same rule then drives the button, the batch endpoint and the two other scoring
// lanes, and a second reason added server-side is honoured here for free.

const SCORE_TITLE = "Scores each image's facial resemblance vs the reference (deletes nothing)";
const NO_REF_TITLE = 'Set a reference photo first';

/** {disabled, title, blocked} for the 🎭 Analyze faces button. */
export function faceAnalysisState({ blockedReason, hasRef, busy } = {}) {
  // A pass that stops running without a word is exactly the failure being fixed —
  // so the reason is the tooltip, and it outranks the missing-reference hint (which
  // would send the user to fix something that would not have helped).
  if (blockedReason) return { disabled: true, title: blockedReason, blocked: true };
  if (!hasRef) return { disabled: true, title: NO_REF_TITLE, blocked: false };
  return { disabled: !!busy, title: SCORE_TITLE, blocked: false };
}

/** Can 🎯 Auto-triage act on the stored face scores?
 *
 * Scores written BEFORE a dataset was marked anime are kept (nothing is deleted —
 * flip the subject type back and they are all still there), but auto-triage is the
 * one surface that ACTS on them: it batch-flips keep/reject. Replaying a threshold
 * over numbers the scorer could not actually measure is silent damage, so the
 * panel withdraws while the dataset is blocked. */
export function autoTriageAvailable(blockedReason) {
  return !blockedReason;
}
