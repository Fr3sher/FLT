import { useState } from 'react';
import Fp8QuantizeTool from './Fp8QuantizeTool.jsx';
import LoraMergeTool from './LoraMergeTool.jsx';

const BUTTON = 'rounded-md border border-sky-300/40 bg-sky-400/15 px-2.5 py-1 text-[0.6875rem] '
  + 'font-semibold text-sky-50 hover:bg-sky-400/25 disabled:opacity-40';
const TOOL_BOX = 'mt-1.5 rounded-md border border-sky-300/30 bg-app/50 px-2 py-1.5';

/** The verbs a delivered full model has beyond "send" and "trash" — the core's
 *  `dense.model.tool` slot (surface `dense`), one per card.
 *
 *  The VERDICT is the core's: `actions` is `denseActions(entry, presence)`, the
 *  panel's own answer to what this entry allows — a quantize button whose
 *  promise is "quantizing fetches it first" cannot be offered once the
 *  repository it would fetch from has been measured gone, and the reason
 *  belongs next to the dead button, before the click, not in a toast after it.
 *  What is drawn here is the buttons, that reason, and the two tools:
 *
 *  - ✨ Quantize to fp8 — the master (here, or fetched from its Hugging Face
 *    repository) into the fp8 file ComfyUI loads, aimed at THIS run's model.
 *  - 🧬 Merge a LoRA in — only for a master that is HERE: merging reads the
 *    whole checkpoint tensor by tensor, so a model that exists only in a
 *    repository has nothing to merge into yet, and offering the button anyway
 *    would be a refusal dressed as an action.
 *
 *  Each card keeps its own open tool. */
export default function DenseModelTools({ entry, busy = false, actions = null }) {
  const [open, setOpen] = useState(null);   // 'quantize' | 'merge' | null
  const quantize = actions?.quantize || null;
  const canMerge = Boolean(entry?.master?.path);
  if (!entry || (!quantize && !canMerge)) return null;
  const toggle = (which) => setOpen((current) => (current === which ? null : which));
  return (
    <>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {quantize && (
          <button type="button" onClick={() => toggle('quantize')}
            disabled={busy || !quantize.enabled}
            title={quantize.reason || undefined}
            className={BUTTON}>
            {open === 'quantize' ? 'Hide' : quantize.label}
          </button>
        )}
        {canMerge && (
          <button type="button" onClick={() => toggle('merge')}
            disabled={busy}
            title="Fold a LoRA into this model's weights and write a new full model"
            className={BUTTON}>
            {open === 'merge' ? 'Hide' : '🧬 Merge a LoRA in'}
          </button>
        )}
      </div>

      {quantize?.reason && (
        <p className="m-0 mt-1 text-content-subtle text-[0.625rem] leading-snug">
          {quantize.reason}
        </p>
      )}

      {open === 'merge' && canMerge && (
        <div className={TOOL_BOX}>
          <LoraMergeTool framed={false} family={entry.train_type}
            base={entry.master.path}
            baseLabel="this run’s full model" />
        </div>
      )}

      {open === 'quantize' && quantize && (
        <div className={TOOL_BOX}>
          <Fp8QuantizeTool framed={false} manualPath={false}
            target={{
              label: 'This run’s full model',
              name: entry.master?.filename || entry.hub?.weight_filename || '',
              sizeBytes: entry.master?.size_bytes || 0,
              family: entry.train_type,
              path: entry.master?.path || null,
              repoId: entry.master ? null : (entry.hub?.repo_id || null),
              filename: entry.master ? null : (entry.hub?.weight_filename || null),
            }} />
        </div>
      )}
    </>
  );
}
