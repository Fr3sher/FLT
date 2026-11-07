import { useState } from 'react';
import { createPortal } from 'react-dom';
import PublishHfModal from './PublishHfModal';
import { HF_EXPORT_ROW, hfExportAvailable } from '../lib/hfExport.js';

/* 🤗 The row in "More ways out" (the dataset workspace's Import & export
   section), contributed to `export.action`: publish this dataset — kept images
   and captions — as a dataset repo on the Hub. The host hands `dataset` and
   `context` (its navigation context: `caps`, `hasKeptImages`…); the row shows
   itself under the same predicate the rail uses for its entry, so a deep link
   never lands on a row that is not there.

   The dialog is portaled to the body: this row lives inside a <details>
   disclosure, and a fixed overlay must not depend on what its ancestors do. */
export default function HfExportAction({ dataset, context }) {
  const [open, setOpen] = useState(false);
  if (!dataset || !hfExportAvailable(context)) return null;
  const configured = Boolean(context.caps?.hf_publish);
  const ready = configured && Boolean(context.hasKeptImages);
  return (
    <div id={HF_EXPORT_ROW.targetId} tabIndex={-1}
      className="flex items-center gap-2 flex-wrap scroll-mt-20">
      {!configured ? (
        <>
          <span className="text-content text-sm">🤗 {HF_EXPORT_ROW.title}</span>
          <p className="text-content-muted text-sm">
            Connect a Hugging Face token with write access to your dataset repository.
          </p>
          <a href="#/plugins/hf_publish/settings" data-workspace-focus
            data-testid="configure-hugging-face"
            className="px-3 py-1.5 rounded-lg bg-surface border border-border text-primary text-sm underline">
            Configure Hugging Face publishing
          </a>
        </>
      ) : <button type="button" data-workspace-focus data-testid="export-hugging-face"
        disabled={!ready}
        onClick={() => setOpen(true)}
        title="Publish this dataset (kept images + captions) as a dataset repo on the Hugging Face Hub. Private by default; you choose the license and confirm you have the right to share."
        className="px-3 py-1.5 rounded-lg bg-surface border border-border text-content text-sm disabled:opacity-50">
        🤗 {HF_EXPORT_ROW.title}
      </button>}
      {configured && <span className="text-content-subtle text-[0.6875rem]">
        {ready ? 'dataset repo on the Hub — private by default' : 'Keep at least one image to publish this dataset.'}
      </span>}
      {open && ready && typeof document !== 'undefined' && createPortal(
        <PublishHfModal datasetId={dataset.id} onClose={() => setOpen(false)} />,
        document.body,
      )}
    </div>
  );
}
