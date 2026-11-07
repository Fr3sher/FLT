/** Where a bottom-left dock may sit, per route.
 * Test Studio owns the bottom edge through StudioActionBar (fixed bottom-0
 * inset-x-0 z-[9960], opaque). A normal bottom-4 dock becomes invisible and
 * unclickable because the bar intercepts clicks.
 * The former PAGES_WITH_BOTTOM_BAR mechanism disappeared while its comment
 * remained. The generation-queue dock repeated the issue (GitHub #44). Keep
 * this placement rule here with a test, not in a comment about a deleted symbol.
 * Move the dock upward, not above the bar in z-order: covering the Run button
 * would defeat the purpose of that bar.
 */

// Routes whose screen can put a fixed bar at the bottom of the window.
//
// Both StudioPage routes do — same shell (App.jsx: '/studio' and
// '/dataset/studio/:id'). Settings is here too: its "Unsaved changes / Save
// changes" bar is `fixed inset-x-0 bottom-4 z-40` — the very same band and the
// very same z-index as the dock, which is rendered after it in the shell and so
// wins at equal z. The offset is UNCONDITIONAL there even though that bar only
// appears while the form is dirty: a dock that jumped a rem the moment you
// edited a field would be worse than one sitting a rem higher all along.
export const ROUTES_WITH_BOTTOM_BAR = ['/studio', '/dataset/studio', '/settings'];

/** Tailwind class for the dock's bottom offset on `pathname`. */
export function dockBottomClass(pathname) {
  const path = String(pathname || '');
  const covered = ROUTES_WITH_BOTTOM_BAR.some(
    (route) => path === route || path.startsWith(`${route}/`),
  );
  // bottom-20 = 5rem, clear of the bar's ~3rem plus its border and the dock's
  // own breathing room.
  return covered ? 'bottom-20' : 'bottom-4';
}
