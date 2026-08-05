/* 🏷️ WHICH pile a caption pass is aimed at, and how many images that really is.
   Pure so the arithmetic behind the button label is unit-tested rather than eyeballed
   in a running app.

   TWO VOCABULARIES, on purpose. The user reads "Kept" and "Undecided"; the wire and the
   database carry 'keep' and 'pending' — the values stored in the status column since the
   bank existed. Renaming either side would break stored filters and saved queries, so the
   translation lives here and nowhere else.

   THE BIN IS NOT AN OPTION. 'reject' is deliberately absent: you curate from what you
   might keep, never from what you threw away, and the server refuses it too (400). */

// The three scopes, in the order the select shows them. The DEFAULT is first and its id
// is '' because it must send NOTHING: a run that picks it has to be byte-identical to the
// pass that existed before this control did — the same contract the vocabulary and length
// selects follow. The other two ids are the column values themselves.
export const CAPTION_SCOPE_OPTIONS = [
  { id: '', label: 'Kept + undecided', short: 'images', statuses: null },
  { id: 'keep', label: '✓ Kept only', short: 'kept', statuses: ['keep'] },
  { id: 'pending', label: 'Undecided only', short: 'undecided', statuses: ['pending'] },
];

export function captionScopeOption(scopeId) {
  return CAPTION_SCOPE_OPTIONS.find((o) => o.id === scopeId) || CAPTION_SCOPE_OPTIONS[0];
}

/** The `statuses` value to POST, or null when the key must be left out entirely. */
export function captionScopeStatuses(scopeId) {
  return captionScopeOption(scopeId).statuses;
}

/** How many images the pass would ACTUALLY caption for this scope.
 *
 *  NOT counts.keep / counts.pending. The pass skips rows that already carry a caption,
 *  so the pile size is not the run size, and quoting the pile would advertise work that
 *  never happens — the mistake the 🧹 Auto-reject counter already paid for once, where a
 *  button offering "5 930 flagged" rejected 0 and read as a broken feature.
 *  The server computes these two numbers with the same filter the job uses. */
export function captionScopeCount(counts, scopeId) {
  const keep = Number(counts?.caption_todo_keep) || 0;
  const pending = Number(counts?.caption_todo_pending) || 0;
  const id = captionScopeOption(scopeId).id;
  if (id === 'keep') return keep;
  if (id === 'pending') return pending;
  return keep + pending;
}

/** Has the server told us the per-scope run sizes yet?
 *
 *  "Not polled yet" is not "zero", and the two must never render as the same 0 — the
 *  rule this payload already follows for `unscanned`. Until the first payload lands the
 *  button keeps its old wording and stays clickable, rather than greying itself out on a
 *  count nobody has measured. */
export function captionCountsKnown(counts) {
  return counts != null && counts.caption_todo_keep !== undefined;
}

/** The button's own words. It states the number it is about to move — a button that
 *  announces one figure and acts on another is the specific misunderstanding this whole
 *  control exists to end. A selection OVERRIDES the scope (see captionScopeDisabled), so
 *  the label switches to the selection and stops quoting a status count. */
export function captionButtonLabel(selectedSize, counts, scopeId) {
  // "up to": the server INTERSECTS the selection with the non-rejected set, so a
  // selection holding rejected or already-captioned images runs shorter than its
  // own size. The pass cannot exceed it, and saying so is the honest bound —
  // quoting a bare `12` for a run of 6 is the same lie the scope counts exist to
  // end, just on the other axis.
  if (selectedSize > 0) return `🏷️ Caption up to ${selectedSize} selected`;
  const opt = captionScopeOption(scopeId);
  if (!captionCountsKnown(counts)) return `🏷️ Caption ${opt.short === 'images' ? 'all' : opt.short}`;
  return `🏷️ Caption ${captionScopeCount(counts, scopeId)} ${opt.short}`;
}

/** Is the scope select inert right now, and why?
 *
 *  A SELECTION WINS. The server intersects the two — "kept only" plus a selection of
 *  undecided images would caption fewer than the button promises — so rather than let a
 *  user build that contradiction, the scope goes inert while a selection is live and the
 *  request omits `statuses` entirely. Returns '' when the control is live. */
export function captionScopeDisabledReason(selectedSize, live) {
  if (live) return 'A pass is already running on this bank.';
  if (selectedSize > 0) {
    return `Your selection decides what gets captioned (${selectedSize} image(s)). `
      + 'Clear it to caption by status instead.';
  }
  return '';
}

/** The sentence under the row: what this run will do, in full, including the two things
 *  a count alone never says — that already-captioned images are skipped, and that the
 *  rejected pile is out of reach whatever is chosen. */
export function captionScopeNote(selectedSize, counts, scopeId) {
  if (selectedSize > 0) {
    return `Captions up to ${selectedSize} selected image(s) that have no caption yet. `
      + 'Rejected images are never captioned.';
  }
  const opt = captionScopeOption(scopeId);
  if (!captionCountsKnown(counts)) {
    return 'Captions the kept and undecided images that have no caption yet. '
      + 'Rejected images are never captioned.';
  }
  const n = captionScopeCount(counts, scopeId);
  if (n === 0) {
    const pile = opt.id === '' ? 'kept or undecided' : opt.short;
    return `Nothing to caption — every ${pile} image already has one.`;
  }
  const what = opt.id === '' ? 'kept and undecided images' : `${opt.short} images`;
  return `Captions the ${n} ${what} that have no caption yet. `
    + 'Rejected images are never captioned.';
}

/* 🔄 RE-CAPTION — the same pass, forced, and the only DESTRUCTIVE thing this row can do.
 *
 * Why it has to exist at all: 🏷️ Caption skips rows that already carry a caption, so on a
 * fully captioned bank its run size is 0 and the button greys out — taking the engine, the
 * model and the pile selects down with it. The dials added beside them would be unreachable
 * on exactly the bank whose captions you want to redo with a better model.
 *
 * WHAT IT DESTROYS, and why we can only count it, never spare it: nothing in this app records
 * WHO wrote a caption. BankImage.caption is one column, written by the pass and copied as-is
 * by the dataset→bank and bank→bank imports; there is no `edited` flag, no second column, no
 * per-caption timestamp. A guard that "protected the hand-written ones" would have to guess
 * from the text — it would mostly skip captions written by a different model and let real
 * short corrections through, and its rule would be invisible from the screen. So the honest
 * design is the one the Dataset already ships: overwrite, but say the number first, and say
 * that hand-edits are in it. bank_undo covers (status, reject_reason) and says in its own
 * header that it offers undo for nothing else — so there is no undo to promise here either.
 */

/** How many images a FORCED run of this scope really walks — captioned or not.
 *
 *  This is NOT captionScopeCount: with force the pass drops its "no caption yet" filter,
 *  so the run size becomes the pile itself (server: _caption_scope_q with no extra filter).
 *  Quoting the uncaptioned count on a re-caption button would understate the run. */
export function captionForcePileSize(counts, scopeId) {
  const keep = Number(counts?.keep) || 0;
  const pending = Number(counts?.pending) || 0;
  const id = captionScopeOption(scopeId).id;
  if (id === 'keep') return keep;
  if (id === 'pending') return pending;
  // The default scope is the server's `status != 'reject'` set. keep + pending is that
  // set exactly — the three piles partition the bank, a fact a backend test pins so an
  // extra status value could never make this number drift in silence.
  return keep + pending;
}

/** How many EXISTING captions a forced run of this scope would overwrite.
 *
 *  The pile minus the part of it that has no caption yet. Both terms come from the same
 *  payload, computed by the same server filter the job uses, so this is arithmetic on
 *  measured numbers rather than a second definition of "captioned". */
export function captionOverwriteCount(counts, scopeId) {
  return Math.max(
    0, captionForcePileSize(counts, scopeId) - captionScopeCount(counts, scopeId));
}

/** The re-caption button's words: the number it will REWRITE (the whole pile), never the
 *  smaller overwrite figure — the button must not quote less than it touches. The count of
 *  destroyed captions belongs to the sentence and the confirmation, which have the room to
 *  name it for what it is.
 *
 *  AND IT DROPS THE NUMBER WHEN IT CANNOT RUN. An inert button still quoting "24 images"
 *  is the same defect one rung down: a figure on screen that no click will act on. Pass
 *  the inert reason (or '') and the label falls back to the bare verb. */
export function captionRecaptionLabel(counts, scopeId, inertReason = '') {
  if (inertReason || !captionCountsKnown(counts)) return '🔄 Re-caption';
  const opt = captionScopeOption(scopeId);
  return `🔄 Re-caption ${captionForcePileSize(counts, scopeId)} ${opt.short}`;
}

/** Is the re-caption button inert right now, and why? '' when it is live.
 *
 *  THE SELECTION CASE IS THE INTERESTING ONE. A selection can span pages that were never
 *  loaded (⬚ Select all fetches ids, not rows), so the client cannot know how many of the
 *  selected images already carry a caption. For a destructive button, "I cannot give you
 *  the number" means "I do not run": re-caption works by pile, and says so. 🏷️ Caption
 *  still honours the selection, so nothing the user could do before is lost. */
export function captionRecaptionDisabledReason(selectedSize, live, counts, scopeId) {
  if (live) return 'A pass is already running on this bank.';
  if (selectedSize > 0) {
    return 'Re-caption works on a whole pile, not on a selection: how many of the '
      + `${selectedSize} selected image(s) already have a caption cannot be counted `
      + 'without loading every one of them, and this button never runs on a number it '
      + 'cannot state. Clear the selection to re-caption by pile.';
  }
  if (!captionCountsKnown(counts)) return 'Waiting for this bank\'s counts.';
  if (captionOverwriteCount(counts, scopeId) === 0) {
    const opt = captionScopeOption(scopeId);
    const pile = opt.id === '' ? 'kept or undecided' : opt.short;
    return `Nothing to re-caption — no ${pile} image has a caption yet. `
      + 'Use 🏷️ Caption to write them first.';
  }
  return '';
}

/** The warning under the row. '' when the button is inert, because a warning about an
 *  action that cannot happen is noise that teaches people to skip warnings. */
export function captionRecaptionNote(selectedSize, live, counts, scopeId) {
  if (captionRecaptionDisabledReason(selectedSize, live, counts, scopeId)) return '';
  const opt = captionScopeOption(scopeId);
  const pile = captionForcePileSize(counts, scopeId);
  const n = captionOverwriteCount(counts, scopeId);
  const what = opt.id === '' ? 'kept and undecided' : opt.short;
  return `🔄 Re-caption rewrites all ${pile} ${what} image(s) with the engine and model `
    + `picked here, overwriting the ${n} caption(s) they already carry. Captions you `
    + 'wrote or corrected by hand look exactly like generated ones to this app — they '
    + 'are overwritten too, and no undo covers captions.';
}

/** The confirmation, worded on the Dataset's own re-caption prompt
 *  (dataset/captionCategory.js: "Re-captioning overwrites the N existing caption(s).
 *  <rule> Continue?") so the app asks this question one way, not two. The bank adds the
 *  two facts the dataset does not have to state: which pile, and that hand-edits are
 *  indistinguishable and unrecoverable. */
export function captionRecaptionConfirmation(counts, scopeId) {
  const opt = captionScopeOption(scopeId);
  const pile = captionForcePileSize(counts, scopeId);
  const n = captionOverwriteCount(counts, scopeId);
  const what = opt.id === '' ? 'kept and undecided' : opt.short;
  return `Re-captioning overwrites the ${n} existing caption(s) among the ${pile} `
    + `${what} image(s). Captions you wrote or corrected by hand cannot be told apart `
    + 'from generated ones and are overwritten too. This cannot be undone. Continue?';
}
