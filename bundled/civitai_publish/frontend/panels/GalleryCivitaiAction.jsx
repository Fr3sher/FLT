import { useEffect, useState } from 'react';
import CivitaiPublishModal from './CivitaiPublishModal';
import { civitaiVerbRefusal } from '../lib/civitaiPublish.js';

/* 📤 The unified viewer's verb — contributed to `lightbox.action` on the gallery
   surface, so every host of GeneratedImageLightbox that shows a library row
   gets it (the Gallery, the Studio viewer, the Canvas). Post this image on
   Civitai, under the model page its checkpoint is linked to, with the prompt,
   seed and settings it was made with. Same footer, same gate (a library row),
   same rule as 📷: disabled with its reason rather than hidden.

   The dialog is a layer of this verb: the host stands its keys down while it
   is open (onLayer), and the next image starts with it closed. The dialog
   addresses the row's own checkpoint stamp, which is the same on every host. */
export default function GalleryCivitaiAction({ img, hasRow = false, disabled = false, onLayer }) {
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [img?.id]);
  useEffect(() => {
    onLayer?.(open);
    return () => onLayer?.(false);
  }, [open, onLayer]);
  if (!hasRow) return null;
  const refusal = civitaiVerbRefusal(img);
  return (
    <>
      <button type="button" data-testid="lightbox-civitai"
        onClick={(e) => { e.stopPropagation(); setOpen(true); }}
        disabled={disabled || !!refusal}
        title={refusal
          || 'Post this image on Civitai, under the model page its checkpoint is linked to, with its prompt, seed and settings'}
        className="min-h-10 lg:min-h-0 inline-flex items-center gap-2 rounded-lg border border-indigo-400/50 bg-indigo-500/20 px-3 py-1.5 text-[0.75rem] font-semibold text-indigo-100 hover:bg-indigo-500/30 disabled:cursor-not-allowed disabled:opacity-45">
        <span aria-hidden>📤</span>
        Civitai
      </button>
      {open && (
        <CivitaiPublishModal context={{ kind: 'image', img }} onClose={() => setOpen(false)} />
      )}
    </>
  );
}
