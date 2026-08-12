/**
 * The little key cap printed on a button that also has a keyboard shortcut.
 *
 * Shared by the Bank's ▶ Review and the dataset's inspection lightbox for the
 * same reason their keys are: the point of ✓ Keep carrying a "K" is that the
 * user learns it once, and two hand-rolled <kbd> styles is how "K" ends up
 * reading like a badge on one screen and like a key on the other.
 *
 * `aria-hidden` on purpose. A screen reader announcing "Keep K" is noise — the
 * button's own title/aria-label already says "(K)" as a sentence.
 */
export default function ShortcutKey({ children }) {
  return (
    <kbd aria-hidden="true"
      className="ml-1 rounded border border-white/25 px-1 text-[10px] font-mono text-white/70">
      {children}
    </kbd>
  );
}
