/* Quand re-demander au serveur le barème adaptatif de steps (`recommended_steps_info`).

   Le barème est calculé SERVEUR à partir du nombre d'images « keep » du dataset.
   Le panneau Training reste monté en permanence (les sections inactives sont
   masquées en display:none pour que le poll de la file continue), donc revenir
   sur l'onglet Train ne remonte rien et ne relançait aucun fetch : si la curation
   avait changé le nombre d'images gardées entre-temps, le barème affiché restait
   celui calculé pour l'ANCIEN nombre. C'est ce qui affichait « ≈1500 · (48 img) »
   avec un rationale disant « 6 images kept », jusqu'à ce qu'un réglage
   d'entraînement soit touché — le seul geste qui relançait le fetch.

   Le nombre d'images gardées est donc une dépendance du fetch, au même titre que
   la base/le type/la variante. Deux nuances :
   - il bouge une image à la fois pendant la curation → on regroupe la rafale ;
   - il bouge surtout pendant qu'une AUTRE section est à l'écran → un appel disque
     (checkpoints, usage disque, lignée) par clic de curation, pour un champ que
     personne ne regarde, serait un mauvais échange. On attend que la section
     Training soit affichée : c'est exactement le moment où le barème doit être
     vrai. */

/** Fenêtre de regroupement (ms) d'une rafale de curation. */
export const STEPS_RECIPE_BURST_MS = 400;

/**
 * Délai avant de refetcher le barème.
 * @param {boolean} visible la section Training est-elle à l'écran
 * @param {?{n_images?: number}} stepsInfo barème actuellement affiché (null = aucun)
 * @param {?number} keptCount nombre d'images gardées maintenant
 * @param {number} [burstMs] fenêtre de regroupement
 * @returns {?number} null = ne rien demander ; 0 = tout de suite (premier
 *   chargement, changement de recette) ; sinon la fenêtre de regroupement.
 */
export function stepsRecipeRefreshDelay(visible, stepsInfo, keptCount,
                                        burstMs = STEPS_RECIPE_BURST_MS) {
  if (!visible) return null;
  const shown = stepsInfo?.n_images;
  // Rien d'affiché, ou serveur plus ancien qui n'annonce pas n_images : on ne peut
  // rien comparer, et laisser l'écran vide 400 ms n'apprend rien à personne.
  if (!Number.isFinite(shown) || !Number.isFinite(keptCount)) return 0;
  return shown === keptCount ? 0 : burstMs;
}
