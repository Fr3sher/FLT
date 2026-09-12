import { useEffect, useSyncExternalStore } from 'react';
import CivitaiPublishModal from './CivitaiPublishModal';
import {
  closeCheckpointPublish, getCheckpointPublish, publishContextOf, subscribeCheckpointPublish,
} from '../lib/checkpointPublishStore.js';

/* 📤 The dialog's mount — contributed to `checkpoint.layer`, which the hosts of
   a checkpoint popover keep mounted (the run graph and the LoRA Canvas). A row asks for a checkpoint; this shows the dialog for
   it and outlives the popover. A link made or removed here changes the pill's
   `civitai` stamp, so the host re-reads its lineage on close (`onChanged`).

   The store is a module singleton: a layer that unmounts with a dialog still
   asked (the user navigated away under it) clears it, or the next host to mount
   a layer would reopen the dialog by itself, on a checkpoint nobody is looking
   at (a refutation finding, 2026-09-05). */
export default function CheckpointCivitaiLayer({ onChanged }) {
  const target = useSyncExternalStore(subscribeCheckpointPublish, getCheckpointPublish, getCheckpointPublish);
  useEffect(() => () => { if (getCheckpointPublish()) closeCheckpointPublish(); }, []);
  if (!target) return null;
  const context = publishContextOf(target);
  return (
    <CivitaiPublishModal context={context}
      onClose={() => {
        const node = target.node ?? null;
        closeCheckpointPublish();
        try { onChanged?.(node); } catch { /* the host's refresh retries on its own */ }
      }} />
  );
}
