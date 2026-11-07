import { openCheckpointPublish } from '../lib/checkpointPublishStore.js';

/* 📤 The checkpoint popover's row — contributed to `checkpoint.action` on both
   surfaces that mount the shared popover (the run graph, the LoRA Canvas):
   publish this checkpoint as a model page, or mark the page it already has so
   the viewer's "post this image" lands under it. The lineage payload stamps the
   link on the pill (`pill.civitai`, the plugin's own `lineage.checkpoints`
   hook), so the row can say which page without a request.

   Never on a run card: a page is made from ONE save. The row only ASKS for the
   dialog (checkpointPublishStore) — the popover unmounts on the click, and the
   dialog is the host-mounted layer's to show. */
const ROW = 'flex items-center gap-1.5 rounded-md border px-2 py-1 text-[0.6875rem] font-medium';

export default function CheckpointCivitaiRow({ node, pill, isRun = false, onClose }) {
  if (isRun || !pill) return null;
  const linked = pill.civitai;
  return (
    <button type="button" onClick={() => { openCheckpointPublish(node, pill); onClose?.(); }}
      data-testid="checkpoint-civitai"
      title={linked
        ? `On Civitai: ${linked.model_name || `model ${linked.model_id}`}${linked.version_name ? ` · ${linked.version_name}` : ''} — open, relink, or post images from the viewer`
        : 'Publish this checkpoint on Civitai, or mark the model page it already has'}
      className={ROW + ' border-indigo-400/40 bg-indigo-500/15 text-indigo-100 hover:bg-indigo-500/25'}>
      <span aria-hidden>📤</span> {linked ? 'On Civitai' : 'Civitai'}
    </button>
  );
}
