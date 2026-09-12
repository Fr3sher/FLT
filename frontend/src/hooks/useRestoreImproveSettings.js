import { improvementAvailable } from '../utils/improveEngines.js';
import { useCallback } from 'react';
import { useToast } from '../components/common/Toast';
import { publishSettings as publishKleinImproveSettings, readImproveSettings, saveImproveSettings } from '../components/dataset/KleinImproveNote';
import {
  restoreImproveMessage, restoreImprovePatch,
} from '../utils/improveSettingsRestore';

/* ↩ "Use these improve settings", as the handler the shared lightbox's
   `onUseImproveSettings` expects — in ONE place, like the improve handler
   itself, because the three hosts (Gallery, checkpoint/run galleries, the ◉
   Canvas) must restore identically or a render restores different settings
   depending on where you happened to open it.

   The settings are FETCHED at click time, not read from a cache: the patch
   depends on the shipped default (to collapse an equal prompt back to '')
   and on today's presets (to name the rows), and both must be current at the
   moment of the write. The saved payload is then PUBLISHED to every mounted
   improve note, so the panel under ✨ quotes the restored instruction
   immediately instead of after its cache TTL. */
export function useRestoreImproveSettings() {
  const toast = useToast();
  const restore = useCallback(async (img) => {
    if (!improvementAvailable('klein')) { toast.warning('Enable Klein Improve before reusing its settings.'); return; }
    try {
      const payload = await readImproveSettings();
      const { patch, report } = restoreImprovePatch({
        img,
        shipped: payload?.identity_prompt_defaults?.klein_improve || '',
        presets: payload?.config?.klein?.generation_lora_presets || [],
      });
      await publishKleinImproveSettings(await saveImproveSettings(patch));
      toast.success(restoreImproveMessage(report));
    } catch (e) {
      toast.error(e?.message || 'Could not apply these improve settings');
    }
  }, [toast]);
  return improvementAvailable('klein') ? restore : undefined;
}
