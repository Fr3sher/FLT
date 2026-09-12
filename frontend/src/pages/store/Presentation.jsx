import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, Image as ImageIcon, X } from 'lucide-react';

const BUTTON = 'inline-flex min-h-10 min-w-10 items-center justify-center gap-2 rounded-md border border-border px-3 py-2 text-sm hover:bg-surface-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary';

export function presentationImages(release) {
  const { id, version } = release.manifest;
  const prefix = `/api/plugins/store/media/${id}/${version}/`;
  return (release.presentation?.images || []).filter((item) => typeof item.url === 'string'
    && item.url.startsWith(prefix)
    && /^[a-z][a-z0-9-]{0,47}\/[0-9a-f]{64}\.(png|jpg|webp)$/.test(item.url.slice(prefix.length))).slice(0, 8);
}

function Screenshot({ item, className = '' }) {
  const [failed, setFailed] = useState(false);
  return failed ? <div role="status" className={`flex items-center justify-center bg-surface-raised p-6 text-sm text-content-muted ${className}`}>
    Screenshot unavailable. You can still read the plugin details.
  </div> : <img src={item.url} alt={item.alt} width={item.width} height={item.height}
    loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(true)}
    className={`bg-surface-raised object-contain ${className}`} />;
}

export function ScreenshotGallery({ images, name, version, onClose }) {
  const [index, setIndex] = useState(0);
  const dialog = useRef(null);
  const titleId = useId();
  const captionId = useId();
  const item = images[index];
  const move = (step) => setIndex((current) => (current + step + images.length) % images.length);

  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = 'hidden';
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, []);

  return createPortal(<dialog ref={dialog} aria-labelledby={titleId} aria-describedby={captionId}
    data-probe-layer data-store-gallery
    onCancel={(event) => { event.preventDefault(); onClose(); }}
    onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
    onKeyDown={(event) => {
      if (event.key === 'Tab') {
        const controls = Array.from(event.currentTarget.querySelectorAll('button:not(:disabled)'));
        const first = controls[0];
        const last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault(); last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault(); first?.focus();
        }
      }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault(); move(event.key === 'ArrowLeft' ? -1 : 1);
      }
    }}
    className="m-auto max-h-[94dvh] w-[calc(100%-1.5rem)] max-w-6xl overflow-hidden rounded-xl border border-border bg-surface p-0 text-content shadow-2xl backdrop:bg-black/80">
    <div className="flex max-h-[93dvh] flex-col p-3 sm:p-5">
      <header className="mb-3 flex shrink-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={titleId} className="break-words text-base font-semibold">{name} screenshots</h2>
          <p className="text-xs text-content-muted">Version {version} · {index + 1} of {images.length}</p>
        </div>
        <button type="button" className={BUTTON + ' shrink-0'} onClick={onClose} aria-label="Close screenshots" autoFocus>
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </header>
      <figure className="flex min-h-0 flex-col">
        <Screenshot key={item.url} item={item} className="min-h-0 max-h-[60dvh] w-full rounded-md" />
        <figcaption id={captionId} aria-live="polite" className="mt-3 max-h-[24dvh] shrink-0 overflow-y-auto break-words text-sm leading-relaxed text-content-muted">
          {item.caption || item.alt}
        </figcaption>
      </figure>
      {images.length > 1 && <nav aria-label="Screenshot navigation" className="mt-4 flex shrink-0 flex-wrap items-center justify-between gap-2">
        <button type="button" className={BUTTON} onClick={() => move(-1)} aria-label="Previous screenshot">
          <ChevronLeft className="h-4 w-4" aria-hidden="true" /><span>Previous</span>
        </button>
        <span className="text-xs text-content-muted">{index + 1} / {images.length}</span>
        <button type="button" className={BUTTON} onClick={() => move(1)} aria-label="Next screenshot">
          <span>Next</span><ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </nav>}
    </div>
  </dialog>, document.body);
}

export default function Presentation({ release }) {
  const [open, setOpen] = useState(false);
  const images = presentationImages(release);
  const { name, version } = release.manifest;
  if (!images.length) return <p className="mb-4 flex items-center gap-2 text-xs text-content-muted" data-store-media="empty">
    <ImageIcon className="h-4 w-4 shrink-0" aria-hidden="true" />Screenshots coming soon
  </p>;
  return <div className="mb-4" data-store-media="available">
    <button type="button" onClick={() => setOpen(true)} aria-label={`View ${name} screenshots`}
      className="block w-full overflow-hidden rounded-lg border border-border text-left hover:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
      <Screenshot key={images[0].url} item={images[0]} className="aspect-video w-full" />
      <span className="flex min-h-10 items-center justify-between gap-2 px-3 py-2 text-xs font-medium">
        <span>View screenshots</span><span className="text-content-muted">{images.length}</span>
      </span>
    </button>
    {open && <ScreenshotGallery key={images.map((image) => image.url).join('|')}
      images={images} name={name} version={version} onClose={() => setOpen(false)} />}
  </div>;
}
