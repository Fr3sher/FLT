import { useEffect } from 'react';

/* 🔍 A checkpoint's generated preview, LARGE.

   The thumbnail on a pill is 14 px by necessity — the pill itself is 60×20 — so
   the image needs somewhere to be actually looked at. Extracted from
   RunLineageGraph.jsx when the LoRA Canvas gained the same pills: on the board
   the thumbnail was clickable and did nothing at all (the host passed no
   handler), which is exactly the silent dead click this app does not ship.

   Esc closes from anywhere through a window listener, not div focus — the
   backdrop is not reliably focused when the image itself is clicked.

   `target` is { url, step } | null. */
export default function PreviewLightbox({ target, onClose }) {
  useEffect(() => {
    if (!target) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [target, onClose]);

  if (!target) return null;
  const step = target.step?.toLocaleString?.() ?? target.step;
  return (
    <div role="dialog" aria-modal="true" aria-label={`Preview at step ${target.step}`}
      data-testid="preview-lightbox"
      className="fixed inset-0 z-[9997] flex flex-col items-center justify-center bg-black/90 p-4"
      onClick={onClose}>
      <button type="button" onClick={(e) => { e.stopPropagation(); onClose?.(); }}
        title="Close (Esc)" aria-label="Close preview"
        className="absolute top-3 right-3 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-lg leading-none text-white hover:bg-white/20">✕</button>
      <img src={target.url} alt={`Generated preview at step ${target.step}`}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[88vh] max-w-full select-none rounded-lg object-contain shadow-2xl" />
      <span className="mt-2 text-white/70 text-[0.75rem] tabular-nums">
        Step {step} · click outside or Esc to close
      </span>
    </div>
  );
}
