/* Why a LOCAL engine (Klein, Krea 2 Edit) can't run on THIS install — one
   answer, shared by every surface that offers those engines.
   PURE JS (no JSX) so `node --test` can exercise it directly.

   WHY THIS FILE EXISTS
   --------------------
   The generation panel had computed Klein's reason inline for a long time, and
   Krea's in utils/kreaEngine.js. That was fine while the generation panel was the
   only place you could pick a local engine. The ✦ Edit-reference modal now offers
   them too, and a second inline copy is how "⚠ Configure ComfyUI in Settings"
   ends up worded one way in one dialog and another way two clicks later — for the
   same missing file. So the reason moved HERE and both callers read it.

   Every branch answers one question: what is the ONE thing to do next? "Not
   available" is an inert button; the user cannot tell a missing weight from a
   stopped ComfyUI from a node pack that needs a restart. */
import { kreaUnavailableReason } from './kreaEngine.js';
import { comfyEnumUnavailableReason } from './comfyEnumSupport.js';
// The REQUIRED-weights vocabulary already exists, next to the Setup step that
// downloads them. Re-listing it here is how the picker and Setup end up naming
// different files for one gap; the recommended LoRA stays excluded there for the
// right reason (optional + auto-fetched, so naming it sends the user nowhere).
import { kleinMissingLabels } from '../hooks/useSetupSteps.js';

/** Why Klein can't be picked, or null when it can. Ordered by what has to be
 *  fixed FIRST — a disabled engine and an unreachable ComfyUI both make the asset
 *  list meaningless.
 *
 *  The enum gap comes BEFORE the weights: a reachable ComfyUI with every file in
 *  place can still refuse a widget VALUE the graph pins (the `beta57` scheduler
 *  took Klein out for everyone without the RES4LYF pack while every other check
 *  went green). Naming the weights there sends the user to re-check a step that
 *  was already correct. */
export function kleinUnavailableReason({
  enabledInSettings = true, comfyuiReachable = true,
  missingAssets = [], unsupportedEnums = [],
} = {}) {
  if (!enabledInSettings) return '⚠ Klein is disabled in Settings (engines)';
  if (!comfyuiReachable) return '⚠ Configure ComfyUI in Settings';
  const enumHint = comfyEnumUnavailableReason(unsupportedEnums);
  if (enumHint) return enumHint;
  const words = kleinMissingLabels(missingAssets);
  // Name the exact missing weight(s) rather than always blaming the UNET: the old
  // text sent users to models/unet/klein/ even when the real gap was the text
  // encoder or the VAE.
  return words.length
    ? `⚠ Klein ${words.join(' + ')} missing — download it in the Setup step`
    : '⚠ Klein model missing — download it in the Setup step (models/unet/klein/)';
}

/** Reason for EITHER local engine, read straight off the capabilities payload.
 *  Returns null for an engine that is available, and for anything that is not a
 *  local engine (an API engine's failures are only knowable from the provider's
 *  answer — nothing here can predict them, and pretending to would be worse).
 *
 *  `enabledEngines` is OPTIONAL: pass the Settings list to honour it, omit it
 *  (null) to skip that gate. The ✦ Edit modal omits it — it does not fetch
 *  /api/settings — which is a known gap, not an opinion: see the follow-up note
 *  in the test file. */
export function localEngineUnavailableReason(engine, caps, enabledEngines = null) {
  const engines = caps?.engines || {};
  const comfy = caps?.comfyui || {};
  const enabled = (e) => (Array.isArray(enabledEngines) ? enabledEngines.includes(e) : true);
  if (engine === 'klein') {
    if (engines.klein) return null;
    return kleinUnavailableReason({
      enabledInSettings: enabled('klein'),
      comfyuiReachable: !!comfy.reachable,
      missingAssets: comfy.klein_missing,
      unsupportedEnums: comfy.klein_unsupported_enums,
    });
  }
  if (engine === 'krea') {
    if (engines.krea) return null;
    return kreaUnavailableReason({
      enabledInSettings: enabled('krea'),
      comfyuiReachable: !!comfy.reachable,
      missingAssets: comfy.krea_missing,
      missingNodes: comfy.krea_nodes_missing,
      invalidAssets: comfy.krea_invalid,
      nodePackInstalled: comfy.krea_nodes_installed,
    });
  }
  return null;
}

/** Whether this install has a ComfyUI at all — the line between "a gap you can
 *  fix from here" and "a product you haven't got". A configured-but-unreachable
 *  ComfyUI counts as HAVING one: it is running-or-not, which is fixable, and
 *  hiding the local engines while the user restarts it would look like the app
 *  lost a feature. Only a wholly unconfigured, unreachable install hides them. */
export function hasComfyui(caps) {
  const comfy = caps?.comfyui || {};
  return !!(comfy.dir_configured || comfy.reachable);
}
