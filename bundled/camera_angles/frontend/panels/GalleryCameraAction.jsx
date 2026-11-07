import { useEffect, useState } from 'react';
import { Camera } from 'lucide-react';
import CameraAnglePicker from './CameraAnglePicker';
import { useCameraAngles } from '../lib/useCameraAngles';
import { cameraRefusal } from '../lib/cameraLane.js';

/* 📷 The unified viewer's verb — contributed to `lightbox.action` on the
   gallery surface, so every host of GeneratedImageLightbox that shows a
   library row gets it for free (the Gallery, the Studio viewer, the Canvas).
   Shown DISABLED with its reason rather than hidden when the row cannot take
   it: a button that vanishes teaches nothing, and "why can't I?" is the
   question that footer exists to answer. A picture the host holds only as a
   URL (no row) gets no verb at all.

   The picker is a layer of this verb: the host stands its keys down while it
   is open (onLayer), Escape peels it first, and the next image starts with it
   closed. */
export default function GalleryCameraAction({ img, hasRow = false, disabled = false, onLayer }) {
  const shoot = useCameraAngles();
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [img?.id]);
  useEffect(() => {
    onLayer?.(open);
    return () => onLayer?.(false);
  }, [open, onLayer]);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); setOpen(false); } };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [open]);
  if (!hasRow) return null;
  const refusal = cameraRefusal(img);
  return (
    <>
      <button type="button" data-testid="lightbox-camera-angles"
        onClick={(e) => { e.stopPropagation(); setOpen(true); }}
        disabled={disabled || !!refusal}
        title={refusal || 'Re-shoot this scene from another camera position'}
        className="min-h-10 lg:min-h-0 inline-flex items-center gap-2 rounded-lg border border-indigo-400/50 bg-indigo-500/20 px-3 py-1.5 text-[0.75rem] font-semibold text-indigo-100 hover:bg-indigo-500/30 disabled:cursor-not-allowed disabled:opacity-45">
        <Camera className="size-3.5" aria-hidden />
        Camera angles
      </button>
      {open && (
        <CameraAnglePicker
          onClose={() => setOpen(false)}
          onShoot={async (poses) => {
            const ok = await shoot(img.id, poses);
            if (ok) setOpen(false);
          }} />
      )}
    </>
  );
}
