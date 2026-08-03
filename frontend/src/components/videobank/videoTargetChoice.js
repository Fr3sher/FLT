/** 🎬 Choosing what to promote a bank INTO — the target, the length, the size.
 *
 * TWO FIELDS OF THE CATALOGUE ARE THE POINT OF THIS FILE, and neither is a
 * footnote:
 *
 *   `training_verified` — whether a LoRA trainer for this target is known to
 *     exist. The app can know a model's geometry perfectly and still have no way
 *     to train it. ONE target out of the four clears this bar. Someone who picks
 *     an unverified one and finds out afterwards has spent a week of cutting,
 *     captioning and GPU time on a dataset nothing can read.
 *
 *   `licence_note` — MiniMax H3's Community Licence grants rights only inside an
 *     "Applicable Territory" that EXCLUDES the EU, the UK, South Korea and the
 *     USA, and the restriction reaches the OUTPUTS. Keeping the training private
 *     is not a way around it. That belongs where the choice is made, not in a
 *     doc nobody opens.
 *
 * Both are therefore surfaced BY THIS MODULE, at the picker, and pinned by tests
 * — a target that quietly loses its warning is a regression, not a tidy-up.
 *
 * THE LENGTH SELECTOR OFFERS FRAME COUNTS FROM THE CATALOGUE, NEVER A FREE FIELD
 * IN SECONDS. The frame rule is a property of each model's VAE, not of video:
 * 29 frames is legal for Wan and illegal for LTX; MiniMax wants f % 17 == 5. A
 * seconds field would produce an illegal count on every keystroke, and the
 * trainers do not refuse it — they floor it in latent space, silently.
 *
 * PURE: no JSX, no fetch.
 */

/** One option of the length selector: the frame count, and what it means in
 * seconds AT THE TARGET'S OWN RATE. Seconds are shown, never entered. */
export function frameOptions(target) {
  if (!target || !Array.isArray(target.frame_choices)) return []
  return target.frame_choices.map((frames) => ({
    frames,
    seconds: clipSeconds(target, frames),
    label: frameOptionLabel(target, frames),
  }))
}

/** "(frames - 1) / fps", because N frames span N-1 intervals. Not cosmetic: it
 * decides how much source a cut needs, and it is why both Wan variants land on
 * exactly 5.00 s at their own rate (81 @ 16, 121 @ 24). Null with no fps. */
export function clipSeconds(target, frames) {
  const fps = target && target.fps
  if (!fps || !frames) return null
  return (frames - 1) / fps
}

export function frameOptionLabel(target, frames) {
  const s = clipSeconds(target, frames)
  return s == null ? `${frames} frames` : `${frames} frames — ${s.toFixed(2)}s`
}

/** The length pre-selected when a target is picked. Null when the catalogue
 * declares none (the "Generic / other" escape hatch). */
export function defaultFrames(target) {
  return (target && target.frame_default) || null
}

/** Does this target hand us a menu, or must the user type a count?
 *
 * "Generic / other" imposes NOTHING — no fps, no rule, no lengths — so it has an
 * empty `frame_choices`. That must render as "we have no verified lengths for
 * this target", never as a silent fallback to Wan's menu, and never as "any
 * length is fine". */
export function needsManualFrames(target) {
  return !!target && (target.frame_choices || []).length === 0
}

/** The size choices. `null` width/height means "keep the source's size", which
 * is the honest default: the catalogue's recommended sizes mirror the models'
 * inference CLIs and are NOT training constraints. */
export function sizeOptions(target) {
  const out = [{
    key: 'source',
    label: 'Source size (no resize)',
    width: null,
    height: null,
  }]
  for (const pair of (target && target.recommended_sizes) || []) {
    const [w, h] = pair
    out.push({ key: `${w}x${h}`, label: `${w} × ${h}`, width: w, height: h })
  }
  return out
}

/** Everything the picker must SHOW about a target, in one object.
 *
 * `warnings` is ordered by what costs the most to discover late: a licence that
 * grants nothing in your country outranks a trainer that does not exist, which
 * outranks anything else. */
export function targetWarnings(target) {
  if (!target) return []
  const out = []
  if (target.licence_note) {
    out.push({ key: 'licence', tone: 'danger', icon: '⚖', text: target.licence_note })
  }
  if (!target.training_verified) {
    out.push({
      key: 'unverified',
      tone: 'warning',
      icon: '⚠',
      text: 'No LoRA trainer is known to exist for this target. You can cut a '
        + 'dataset for it, but nothing is known to train on it yet.',
    })
  }
  if (target.keep_audio) {
    out.push({
      key: 'audio',
      tone: 'info',
      icon: '🔊',
      text: 'This target trains audio and video together — the soundtrack is kept, '
        + 'and captions should describe it.',
    })
  }
  return out
}

/** The one-line badge next to a target's name in the list. Short on purpose:
 * the full sentence is in the warnings below the picker. */
export function targetBadge(target) {
  if (!target) return null
  if (target.licence_note) return { tone: 'danger', text: 'Licence limits' }
  if (!target.training_verified) return { tone: 'warning', text: 'Not trainable yet' }
  return { tone: 'ok', text: 'Trainable' }
}

/** A client-side refusal, or null. Duplicating the server's checks is NOT the
 * goal — the server refuses authoritatively. This exists so the dialog can grey
 * its own button out and say why, instead of round-tripping a 400. */
export function promoteProblem({ name, target, frames }) {
  if (!(name || '').trim()) return 'Name the dataset first.'
  if (!target) return 'Pick a target model first.'
  if (!frames) {
    return needsManualFrames(target)
      ? `${target.label} declares no clip lengths — type a frame count.`
      : 'Pick a clip length.'
  }
  if (!Number.isInteger(frames) || frames <= 0) {
    return 'A clip length is a whole number of frames.'
  }
  return null
}

/** The POST body for /video-bank/<id>/promote.
 *
 * `ids` is OMITTED when the selection is empty, because an empty list means
 * EVERY KEPT CLIP on the server — the caller must have decided that on purpose,
 * and it always goes through this function so the two cannot drift.
 *
 * `width`/`height` ride together or not at all: the server treats "both present"
 * as a resize and anything else as "keep the source's size", so sending a lone
 * width would silently be ignored. */
export function promotePayload({ name, targetKey, frames, size, ids }) {
  const body = {
    name: (name || '').trim(),
    target_profile: targetKey,
    frames,
  }
  if (size && size.width && size.height) {
    body.width = size.width
    body.height = size.height
  }
  if (Array.isArray(ids) && ids.length > 0) body.ids = ids
  return body
}

/** What the confirm button is about to do, spelled out. "Promote" alone hides
 * whether it takes the selection or the whole bank, and those differ by an order
 * of magnitude in GPU minutes. */
export function promoteScopeLabel(selectedCount, keepCount) {
  if (selectedCount > 0) {
    return `${selectedCount} selected clip${selectedCount === 1 ? '' : 's'}`
  }
  return `all ${keepCount} kept clip${keepCount === 1 ? '' : 's'}`
}
