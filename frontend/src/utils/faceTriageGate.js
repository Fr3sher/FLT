/* FIDELITY-AWARE AUTO-TRIAGE GATE — decide keep/reject from a face verdict.
 *
 * The historical auto-triage only threshold-decided `scorable` faces and left
 * every non-scorable verdict (`too_small`, `no_face`, `low_det`, `extreme_pose`)
 * to manual review — which is how a bank like G1_AI ended up with 82/96 images
 * whose faces were too small and nothing done about it. This gate closes that
 * gap and makes the verdict depend on the dataset's FIDELITY, because a body
 * LoRA and a face LoRA want different things:
 *
 *   face fidelity : the face IS the product  -> too_small / low_det / no_face reject
 *   body fidelity : the body is the product  -> keep too_small / low_det / profile
 *   no_face        : reject in BOTH — a shot with no detectable face at all can
 *                    never contribute identity, whatever the fidelity.
 *
 * `scorable` faces keep the threshold rule: score >= t keep, below reject. Pure
 * function, no React, so `node --test` covers the verdict table directly.
 */

const NON_SCORABLE = ['no_face', 'low_det', 'too_small', 'extreme_pose'];

/** Is `img` a face verdict auto-triage can act on (vs unscored / error rows)? */
export function isAutoTriagable(img) {
  if (!img || !img.filename) return false;
  const s = img.face_state;
  if (s === 'scorable') return img.face_score != null;
  return NON_SCORABLE.includes(s);
}

/** The auto-triage verdict for `img`: 'keep' | 'reject' | null (leave alone). */
export function autoTriageDecision(img, threshold, bodyFidelity) {
  if (img.face_state === 'scorable' && img.face_score != null) {
    return img.face_score >= threshold ? 'keep' : 'reject';
  }
  switch (img.face_state) {
    case 'no_face':
      return 'reject';
    case 'too_small':
    case 'low_det':
    case 'extreme_pose':
      return bodyFidelity ? 'keep' : 'reject';
    default:
      return null; // unscored / unknown -> leave for manual review
  }
}
