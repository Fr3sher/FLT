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
  if (selectedSize > 0) return `🏷️ Caption ${selectedSize} selected`;
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
