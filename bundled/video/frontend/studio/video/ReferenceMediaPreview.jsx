import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Maximize2, Minimize2, X, ZoomIn } from 'lucide-react';
import { useFocusTrap } from '@lds/plugin-sdk/ui';

const ACTION = 'inline-flex min-h-10 min-w-10 items-center justify-center gap-2 rounded-md border border-border px-2 text-xs text-content hover:bg-surface-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary';

function ReferenceLightbox({ kind, src, label, description, startTime, onClose }) {
  const dialog = useRef(null);
  const [originalSize, setOriginalSize] = useState(false);
  const [failed, setFailed] = useState(false);
  useFocusTrap(dialog);
  useEffect(() => {
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const key = (event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      onClose();
    };
    window.addEventListener('keydown', key, true);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener('keydown', key, true);
    };
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-[9500] flex items-center justify-center bg-black/85 p-2 sm:p-4"
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div ref={dialog} role="dialog" aria-modal="true" aria-label={`Preview ${label}`}
        data-probe-chrome="reference-preview" data-probe-layer
        className="flex h-[calc(100dvh-2rem)] min-h-0 w-full max-w-6xl flex-col gap-2 rounded-xl border border-border bg-surface-overlay p-2 sm:p-3">
        <header className="flex shrink-0 items-center gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-semibold text-content">{label}</h3>
            {description && <p title={description} className="truncate text-xs text-content-muted">{description}</p>}
          </div>
          {kind === 'image' && !failed && <button type="button" className={ACTION}
            onClick={() => setOriginalSize((value) => !value)} aria-pressed={originalSize}
            aria-label={originalSize ? 'Fit to screen' : 'Show original size'} title={originalSize ? 'Fit to screen' : 'Show original size'}>
            {originalSize ? <Minimize2 className="h-4 w-4" /> : <ZoomIn className="h-4 w-4" />}
          </button>}
          <button type="button" className={ACTION} onClick={onClose} aria-label="Close reference preview" title="Close (Esc)"><X className="h-4 w-4" /></button>
        </header>
        <div className={`min-h-0 flex-1 rounded-lg bg-black ${originalSize ? 'overflow-auto' : 'flex items-center justify-center overflow-hidden'}`}>
          {failed ? <p role="alert" className="p-4 text-sm text-content-muted">This reference could not be loaded.</p>
            : kind === 'image' ? <img src={src} alt={description || label} onError={() => setFailed(true)}
              className={originalSize ? 'block max-w-none' : 'max-h-full max-w-full object-contain'} />
              : <video src={src} controls autoPlay muted playsInline tabIndex={0} aria-label={label}
                onLoadedMetadata={(event) => { if (startTime > 0) event.currentTarget.currentTime = Math.min(startTime, event.currentTarget.duration || startTime); }}
                onError={() => setFailed(true)} className="h-full w-full object-contain" />}
        </div>
        {originalSize && <p className="shrink-0 text-xs text-content-muted">Original size · scroll to inspect the image.</p>}
      </div>
    </div>, document.body,
  );
}

/** Preview uses the exact staged media that the generation will receive. */
export default function ReferenceMediaPreview({ kind = 'image', src, label, description }) {
  const player = useRef(null);
  const [preview, setPreview] = useState(null);
  const open = () => {
    const startTime = player.current?.currentTime || 0;
    player.current?.pause();
    setPreview({ startTime });
  };
  return (
    <div className="flex w-full min-w-0 flex-col items-center gap-1">
      {kind === 'image' ? <button type="button" onClick={open} aria-label={`Enlarge ${label}`} title="Enlarge reference"
        className="relative flex min-h-10 w-full cursor-zoom-in items-center justify-center rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
        <img src={src} alt={description || label} className="max-h-36 max-w-full rounded object-contain" />
        <span aria-hidden="true" className="absolute bottom-1 right-1 rounded bg-black/75 p-1 text-white"><Maximize2 className="h-4 w-4" /></span>
      </button> : <>
        <video ref={player} src={src} controls muted playsInline preload="metadata" aria-label={label} className="max-h-36 w-full rounded" />
        <button type="button" onClick={open} className={`${ACTION} w-full`} aria-label={`Enlarge ${label}`}><Maximize2 className="h-3.5 w-3.5" />Enlarge</button>
      </>}
      {preview && <ReferenceLightbox key={src} kind={kind} src={src} label={label} description={description}
        startTime={preview.startTime} onClose={() => setPreview(null)} />}
    </div>
  );
}
