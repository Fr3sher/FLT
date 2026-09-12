import { useState } from 'react';
import { Dna } from 'lucide-react';
import LoraMergeTool from './LoraMergeTool.jsx';
import { loadMergeOpen, saveMergeOpen } from '../lib/loraMerge.js';

/** The LoRA merge in the dataset's Checkpoints & LoRAs panel — the core's
 *  `training.tool` slot (surface `dataset`).
 *
 *  Merging needs no dense run of its own — the usual case is a LoRA trained
 *  here folded into a base downloaded from anywhere — and the full-model cards
 *  render NOTHING when a dataset has no full model. So the tool lives here
 *  too, always reachable, collapsed because most visits to that panel are not
 *  about it. (Inside a full model's card it appears again, with the base
 *  pre-filled — DenseModelTools.jsx.)
 *
 *  The disclosure is CONTROLLED, and persisted. `open` on a <details> is DOM
 *  state, and the block lives inside the panel's CheckpointPortal — every swap
 *  between the portal host and the inline place unmounts it, which once closed
 *  the tool on top of emptying it. The persisted value is read back on every
 *  mount, so the remount restores it and not only a reload.
 *
 *  `family` is the family the panel's checkpoint filter is on, so a merge's
 *  LoRA rows are checked against it. */
export default function TrainingMergeTool({ family }) {
  const [mergeOpen, setMergeOpen] = useState(loadMergeOpen);
  const toggleMerge = (event) => {
    event.preventDefault();
    const next = !mergeOpen;
    setMergeOpen(next);
    saveMergeOpen(next);
  };
  return (
    <details open={mergeOpen}
      className="rounded-lg border border-border bg-surface-raised px-3 py-2">
      <summary onClick={toggleMerge}
        className="min-h-10 lg:min-h-0 cursor-pointer text-content text-xs font-semibold">
        <Dna aria-hidden="true" className="mr-1 inline h-3.5 w-3.5 align-[-2px]" />Merge a LoRA into a base checkpoint
      </summary>
      <p className="m-0 mt-1 text-content-subtle text-[0.625rem] leading-relaxed">
        Folds one or more LoRAs into a full-precision checkpoint and writes a new
        full model — the step between “I trained a LoRA” and “I have a model to
        publish”. Nothing is overwritten, and the result says in its own metadata
        that it is a merge and not a training run.
      </p>
      <div className="mt-1.5">
        <LoraMergeTool framed={false} family={family} />
      </div>
    </details>
  );
}
