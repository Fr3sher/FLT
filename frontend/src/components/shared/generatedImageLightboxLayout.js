/* WHERE THE FACTS PANEL SITS — the one decision, in one place.
 *
 * The generated-image lightbox has two shapes: image over facts (stacked), or
 * image beside facts (split). The shape is chosen by ONE breakpoint, and the
 * breakpoint used to be `lg` (1024 px).
 *
 * ⚠️ WHY THAT WAS WRONG, measured rather than argued. A tablet held in
 * LANDSCAPE reports ~900-960 CSS px, not the ~1850 physical px on its spec
 * sheet — the device pixel ratio eats the difference. So the widest, most
 * horizontal screen most people open this on landed one notch UNDER the split
 * and got the phone layout: at 923x520 the picture was drawn 179x262 — 9 % of
 * the viewport — with a full-width band of chips, settings and buttons pushed
 * below the fold. The layout was not wrong at any width; it started too late.
 *
 * `md` (768 px) is the honest floor. Below it a bounded reading column plus an
 * image column is a lie: at 640 px the panel would take half the screen and the
 * picture would be a stamp beside it, which is the same failure mirrored. So
 * under `md` the stack stays, and it stays deliberately — the image takes the
 * height it can and the facts scroll under it.
 *
 * ⚠️ AND WIDTH ALONE IS NOT THE QUESTION — ORIENTATION IS THE OTHER HALF. A
 * 900x2000 portrait tablet clears 768 px and is still the wrong shape for a
 * rail: measured, splitting it drew the picture 556x813 where the stack drew it
 * 832x1216. The scarce axis on a portrait screen is WIDTH, and a side column
 * spends exactly that. So the split asks for both: at least `md` wide AND
 * `landscape` (a plain `(orientation: landscape)` media query, i.e. wider than
 * tall). Every case then falls out right without naming any device — a tablet
 * held sideways splits, the same tablet stood up stacks, a desktop window
 * dragged taller than it is wide stacks, a phone never splits.
 *
 * THE PANEL WIDTH GROWS WITH THE SCREEN, between two hard bounds:
 *  - never under MIN_PANEL_PX, or "✨ Upscale & improve" and the Klein model
 *    picker wrap into unreadable stubs;
 *  - never over MAX_PANEL_PX, because the whole point of the column is a
 *    PARAGRAPH's reading width — a prompt set 900 px wide is the wall of text
 *    this component was written to end.
 * Between them the image gets every pixel that is left, which is the axis the
 * user is actually looking at.
 *
 * These are Tailwind class strings rather than computed styles on purpose: the
 * shape must be right on the FIRST paint, before any measurement, and a
 * resize must not run JavaScript. They live here, not inline in the JSX, so
 * `node --test` can assert the breakpoint and the bounds without a DOM.
 */

/** Viewport width at which the panel moves beside the image (Tailwind `md`). */
export const SPLIT_MIN_WIDTH_PX = 768;

/** Narrowest the facts column is ever drawn, in px (`w-[20rem]`). */
export const MIN_PANEL_PX = 320;

/** Widest the facts column is ever drawn, in px (`xl:w-[27rem]`). */
export const MAX_PANEL_PX = 432;

/** Every responsive utility that turns the stack into a split carries this
 *  prefix — and it is ONE string so the two halves can never disagree about
 *  when they change shape (a panel that goes to the side while the shell is
 *  still a column is a blank screen with a stripe). */
export const SPLIT_VARIANT = 'md:landscape:';

/** The overlay: a column, and a row once it is wide enough AND landscape. */
export const SHELL_CLASS = 'fixed inset-0 z-[9997] flex flex-col bg-black/95 md:landscape:flex-row';

/** The image half. `min-h-0`/`min-w-0` so a tall picture cannot push the panel
 *  out of the viewport instead of shrinking itself. */
export const IMAGE_PANE_CLASS = 'flex min-h-0 min-w-0 flex-1 items-center justify-center p-3';

/** The picture. `object-contain` keeps the aspect; the height cap is what makes
 *  it fill the column rather than sit small and centred at the top. */
export const IMAGE_CLASS = 'max-h-full max-w-full select-none rounded-lg object-contain shadow-2xl';

/** The facts column. Stacked: a bounded band under the image with its own
 *  scroll. Split: a full-height bordered column of bounded width. */
export const FACTS_PANEL_CLASS = 'max-h-[45vh] w-full shrink-0 overflow-y-auto '
  + 'border-t border-white/10 bg-app px-3 py-2.5 '
  + 'md:landscape:max-h-none md:landscape:h-full md:landscape:w-[20rem] '
  + 'md:landscape:border-l md:landscape:border-t-0 md:landscape:px-4 md:landscape:py-10 '
  + 'lg:landscape:w-[24rem] xl:landscape:w-[27rem]';
