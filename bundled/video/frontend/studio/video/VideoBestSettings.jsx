import { useEffect, useState } from 'react';
import { Star, Trash2 } from 'lucide-react';
import { apiFetch, del, postJson } from '@lds/plugin-sdk';
// The extension disambiguates this file from its own name: `videoBestSettings.js`
// and `VideoBestSettings.jsx` are the same path on Windows and macOS, so a bare
// specifier resolved with .jsx first imports THIS component from itself.
import { bestForLoraUrl, saveVideoBestUrl, videoBestUrl } from './videoBestSettings.js';

export function useVideoBestSettings(lora, toast) {
  const { lora: filename, runId, datasetId } = lora;
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    setState(null); setError('');
    if (filename) apiFetch(bestForLoraUrl({ lora: filename, runId, datasetId })).then((data) => {
      if (current) setState(data);
    }).catch((e) => { if (current) setError(e.message || 'Could not read best settings.'); });
    return () => { current = false; };
  }, [filename, runId, datasetId]);

  const save = async (clip) => {
    if (clip.mode === 'ref2va' || clip.generation_settings?.refmods) {
      toast.info('Best settings do not support References yet. Use Reuse on this clip.'); return;
    }
    setBusy(true);
    try {
      const out = await postJson(saveVideoBestUrl(clip.id), {});
      setState({ dataset_id: out.best_settings.dataset_id, best_settings: out.best_settings });
      setError('');
      toast.success('Best settings saved for this video dataset.');
    } catch (e) {
      toast.error(e.message || 'Could not save best settings.');
    } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try {
      await del(videoBestUrl(state.dataset_id));
      setState((s) => ({ ...s, best_settings: null }));
      toast.success('Best settings removed.');
      return true;
    } catch (e) {
      toast.error(e.message || 'Could not remove best settings.');
      return false;
    } finally { setBusy(false); }
  };
  return { state, busy, error, save, remove };
}

export default function VideoBestSettings({ state, busy, error, onApply, onRemove, referenceMode = false }) {
  const best = state?.best_settings;
  if (!best && !error) return null;
  return (
    <section data-probe-panel="video-best-settings" className="flex min-w-0 flex-col gap-2 rounded-xl border border-primary/40 bg-surface p-3">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-content">
        <Star aria-hidden="true" className="h-4 w-4 text-primary" />Best settings
      </h3>
      {error && <p className="text-xs text-content-muted">{error}</p>}
      {best && <>
        <p className="break-words text-xs text-content-muted">{best.lora_filename}</p>
        <p className="text-xs text-content-subtle">Saved from clip #{best.clip_id}. Apply the generation settings to your current scene. Smoothing and neural rendering are separate passes.</p>
        {referenceMode && <p className="text-xs text-content-muted">Best settings do not support References yet. Use Reuse on a reference clip to restore its settings.</p>}
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={busy || referenceMode || best.settings?.mode === 'ref2va'} onClick={() => onApply(best)} className="min-h-10 rounded-lg border border-primary/40 bg-primary/10 px-3 py-1 text-xs text-content disabled:opacity-50 lg:min-h-0">Apply best settings</button>
          <button type="button" disabled={busy} onClick={onRemove} className="flex min-h-10 items-center gap-1 rounded-lg border border-border px-3 py-1 text-xs text-content-muted disabled:opacity-50 lg:min-h-0"><Trash2 aria-hidden="true" className="h-3.5 w-3.5" />Remove</button>
        </div>
      </>}
    </section>
  );
}
