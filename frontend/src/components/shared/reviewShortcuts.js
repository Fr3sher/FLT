/**
 * ONE keyboard grammar for judging images, wherever the app shows a picture
 * full-size: K keep · R reject · S skip · ← back · Esc close.
 *
 * The Bank's ▶ Review lightbox taught it, and the dataset's inspection lightbox
 * now speaks the same one — reading it from HERE rather than from a second
 * hand-written copy. Two copies is precisely how ✓ ends up on K in one screen
 * and on Enter in the other, and a reflex that is right half the time is worse
 * than no reflex at all. The printed hint comes from here too, so what the UI
 * PROMISES cannot drift from what the handler does either.
 *
 * Pure and DOM-free on purpose: `node --test` cannot render JSX, so the part
 * worth testing — which keystroke means what, and which keystrokes must be left
 * alone — lives outside the components that listen for it.
 *
 * Each surface still owns what is its own: the Bank adds [ ] rotate and M mask,
 * the dataset lightbox peels its phone actions panel before it closes. This
 * module answers the shared question only, and returns null for everything else
 * so the caller can go on reading the event.
 */

/** The shortcut line printed under the buttons, in both lightboxes. */
export const REVIEW_SHORTCUT_HINT = 'K keep · R reject · S skip';

/**
 * Does the focused element own this keystroke?
 *
 * ONLY text entry does. A blanket `tagName === 'input'` guard once killed K/R/S
 * outright in the Bank: the focus trap lands on the 🎲 Random-order checkbox
 * when the lightbox opens, so every shortcut did nothing until you clicked
 * somewhere else. A checkbox, a radio, a button and a slider do not consume
 * letters — a textarea, a select, a text field and a contenteditable do.
 */
export function ownsTypedKeys(target) {
  if (!target || typeof target !== 'object') return false;
  if (target.isContentEditable) return true;
  const tag = typeof target.tagName === 'string' ? target.tagName.toLowerCase() : '';
  const type = typeof target.type === 'string' ? target.type.toLowerCase() : '';
  if (tag === 'textarea' || tag === 'select') return true;
  return tag === 'input'
    && !['checkbox', 'radio', 'button', 'submit', 'range'].includes(type);
}

/**
 * What this keystroke means for a review surface:
 * 'keep' | 'reject' | 'skip' | 'back' | 'close' | null.
 *
 * `null` means "not mine" — the caller may still read the event for its own
 * keys. A modified keystroke is never ours: ⌘R reloads, ⌥← is browser history
 * and ⇧→ extends a selection, and stealing any of those would be a bug the user
 * blames on the app.
 *
 * Escape is answered BEFORE the typing guard: a field focused inside an overlay
 * must never be able to trap the user in it.
 *
 * → is the same action as S deliberately. Moving on without judging IS a skip:
 * the image keeps whatever status it already had, which is the one promise that
 * makes a fast walk safe.
 */
export function reviewKeyAction(event) {
  if (!event) return null;
  if (event.metaKey || event.ctrlKey || event.altKey) return null;
  if (event.key === 'Escape') return 'close';
  if (event.shiftKey) return null;
  if (ownsTypedKeys(event.target)) return null;
  const key = typeof event.key === 'string' ? event.key : '';
  const letter = key.toLowerCase();
  if (letter === 'k') return 'keep';
  if (letter === 'r') return 'reject';
  if (letter === 's' || key === 'ArrowRight') return 'skip';
  if (key === 'ArrowLeft') return 'back';
  return null;
}
