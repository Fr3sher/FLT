/* Krea 2 Identity Edit — the pure, testable half of the engine's UI.
   PURE JS (no JSX) so `node --test` can import and exercise it directly, the
   same split as engineSelection.js.

   WHY THIS FILE EXISTS
   --------------------
   "Other people don't have my install." Krea needs FOUR weight files AND a
   community custom-node pack, and each of those can be missing for a different
   reason with a different fix. A card that just greys out with "not available"
   is an inert button; the user has no idea whether to install a node pack, drop
   a LoRA somewhere, or fix their ComfyUI URL. So the reason is computed here,
   from the capabilities payload, and it is unit-tested — one branch per real
   failure mode, in the order the user must fix them. */

/** Setup/capabilities asset keys -> the words a sentence uses. Mirrors
 *  krea_edit_helper.KREA_ASSETS; an unknown key falls back to itself rather
 *  than disappearing from the message. */
export const KREA_ASSET_LABELS = {
  krea_model: 'base model',
  krea_identity_lora: 'identity edit LoRA',
  krea_text_encoder: 'text encoder',
  krea_vae: 'VAE',
};

/** Stable-order words for the missing assets, so the sentence reads the same
 *  way every time regardless of how the server ordered the list. */
export function kreaMissingLabels(missing) {
  const set = new Set(Array.isArray(missing) ? missing : []);
  return Object.keys(KREA_ASSET_LABELS)
    .filter((k) => set.has(k))
    .map((k) => KREA_ASSET_LABELS[k]);
}

export const KREA_NODE_PACK_URL = 'https://github.com/lbouaraba/comfyui-krea2edit';

/** Why the Krea engine can't be picked, or null when it can.
 *  Ordered by what the user has to do FIRST: a disabled engine and an
 *  unreachable ComfyUI both make the asset lists meaningless, and the node pack
 *  comes before the weights because without it nothing can run even with every
 *  file in place. */
export function kreaUnavailableReason({
  enabledInSettings = true, comfyuiReachable = true,
  missingAssets = [], missingNodes = [],
} = {}) {
  if (!enabledInSettings) return '⚠ Krea 2 Edit is disabled in Settings (engines)';
  if (!comfyuiReachable) return '⚠ Configure ComfyUI in Settings';
  if (Array.isArray(missingNodes) && missingNodes.length) {
    return '⚠ Install the comfyui-krea2edit node pack in ComfyUI, then restart it';
  }
  const words = kreaMissingLabels(missingAssets);
  if (words.length) return `⚠ Krea ${words.join(' + ')} missing — see Setup for where to place it`;
  return null;
}

/** What the grounding dial currently means, in one short phrase. The number
 *  alone tells nobody anything; this is the whole point of exposing it. */
export function groundingDescription(px) {
  const n = Number(px);
  if (!Number.isFinite(n) || n <= 0) return 'default (1024)';
  if (n <= 640) return `${n}px · follows the prompt, looser likeness`;
  if (n < 1024) return `${n}px · leans towards the prompt`;
  if (n === 1024) return `${n}px · balanced (recommended for people)`;
  if (n <= 1280) return `${n}px · leans towards the reference`;
  return `${n}px · sticks to the reference, may ignore the shot`;
}
