import { useEffect, useState } from 'react';
import CameraAnglePicker from './CameraAnglePicker';
import { useDatasetCameraAngles } from '../lib/useDatasetCameraAngles';
import { datasetCameraRefusal } from '../lib/cameraLane.js';

/* 📷 The dataset lightbox's verb — contributed to `lightbox.action` on the
   dataset surface. With the improve group because it answers the same
   question from the other side: ✨ makes THIS picture better, 📷 makes MORE
   pictures of this scene. The results are new pending candidates, so the
   button must not read as an edit of the file on screen — the title says
   where they land.

   Eligibility is decided HERE (datasetCameraRefusal): a picture that cannot
   take it shows no button, the way the host used to decide it. The picker is
   a layer of this verb: while it is open the host stands its keys down
   (onLayer), Escape peels it first, and moving to another image closes it —
   an open picker is a moment on THIS image. */
export default function DatasetCameraAction({ img, disabled = false, onLayer }) {
  const shoot = useDatasetCameraAngles();
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
  if (!img || img._rescueReviewPreview || datasetCameraRefusal(img) !== null) return null;
  return (
    <>
      <button type="button" data-testid="dataset-camera-angles"
        onClick={(e) => { e.stopPropagation(); setOpen(true); }}
        disabled={disabled}
        title="Re-shoot this scene from other camera positions — the views arrive as new pending candidates of this dataset, with the angle already in the caption"
        className="min-h-10 lg:min-h-9 w-full sm:w-auto px-3 py-1.5 rounded-lg border border-indigo-400/50 bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-100 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-45">
        <span aria-hidden>📷</span> Camera angles
      </button>
      {/* Above the lightbox (its z-index outranks the dialog's), so the picture
          stays visible behind the dial while positions are chosen — picking an
          angle of something you cannot see is guesswork. */}
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
