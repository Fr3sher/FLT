/* When to refetch the adaptive server steps recipe (recommended_steps_info).
   The server derives it from kept-image count. Training stays mounted while
   hidden so queue polling continues; returning to Train does not remount or
   refetch. After curation, the old count therefore remained until a training
   setting changed (for example, a 48-image dataset showing a 6-image recipe).

   Depend on kept count as well as base/type/variant. Batch rapid curation
   changes and defer while Training is hidden: reading checkpoints, disk usage
   and lineage after every curation click is unnecessary for an invisible field.
   Refresh when Training becomes visible, when the recipe must be accurate. */

/** Debounce window (ms) for a burst of curation changes. */
export const STEPS_RECIPE_BURST_MS = 400;

/**
 * Delay before refetching the steps recipe.
 * @param {boolean} visible whether Training is visible
 * @param {?{n_images?: number}} stepsInfo displayed recipe (null = none)
 * @param {?number} keptCount current kept-image count
 * @param {number} [burstMs] debounce window
 * @returns {?number} null = no request; 0 = immediate (initial load or recipe
 *   change); otherwise the debounce window.
 */
export function stepsRecipeRefreshDelay(visible, stepsInfo, keptCount,
                                        burstMs = STEPS_RECIPE_BURST_MS) {
  if (!visible) return null;
  const shown = stepsInfo?.n_images;
  // Without a displayed recipe, or n_images from an older server, there is
  // nothing to compare. Do not leave the screen empty for another 400 ms.
  if (!Number.isFinite(shown) || !Number.isFinite(keptCount)) return 0;
  return shown === keptCount ? 0 : burstMs;
}
