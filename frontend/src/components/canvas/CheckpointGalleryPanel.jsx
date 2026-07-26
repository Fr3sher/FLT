import { useEffect, useState } from 'react';
import { apiFetch } from '../../api/fetchClient';

/* 🖼 Everything one checkpoint ever produced.

   Images used to be attached to a checkpoint by PARSING the LoRA's filename on
   every render, and a checkpoint could hold exactly one preview — regenerating
   replaced it. Both are gone: the link is a pair of columns written when the
   image is generated, and previews accumulate. So a pill can now open a real
   history, whatever produced it — an inline canvas preview, a Test-Studio grid
   cell, a comparison run.

   `unlinked` is stated, not hidden. Images generated before the columns existed,
   whose filename carries no run tag, cannot be attributed to a checkpoint
   without guessing — so they are not shown under one, and the panel says how
   many there are. An incomplete history that says so beats a tidy one that lies. */
export default function CheckpointGalleryPanel({ target, onClose }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: null });
  const [zoom, setZoom] = useState(null);

  useEffect(() => {
    if (!target) return undefined;
    let alive = true;
    setState({ status: 'loading', data: null, error: null });
    apiFetch(`/api/train/checkpoint/${target.recordId}/${target.step}/images`)
      .then((d) => { if (alive) setState({ status: 'ready', data: d, error: null }); })
      .catch((e) => {
        if (alive) {
          setState({ status: 'error', data: null,
            error: e?.message || 'Could not load this checkpoint’s images' });
        }
      });
    return () => { alive = false; };
  }, [target?.recordId, target?.step]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!zoom) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setZoom(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoom]);

  if (!target) return null;
  const d = state.data;

  return (
    <>
      <aside
        data-testid="checkpoint-gallery-panel"
        aria-label={`Images generated at step ${target.step}`}
        className="fixed inset-x-0 bottom-0 z-50 flex max-h-[70vh] flex-col overflow-hidden border-t border-border bg-surface-overlay shadow-xl
                   sm:inset-x-auto sm:left-0 sm:top-0 sm:h-full sm:max-h-none sm:w-[22rem] sm:border-r sm:border-t-0">
        <header className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2">
          <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-content">
            <span aria-hidden>🖼</span> Step {target.step}
            <span className="font-normal text-content-muted"> · run #{target.recordId}</span>
          </h3>
          <button type="button" onClick={onClose} aria-label="Close"
            className="shrink-0 text-content-subtle hover:text-content">✕</button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {state.status === 'loading' && (
            <p className="m-0 text-content-subtle text-[0.75rem]">Loading…</p>
          )}
          {state.status === 'error' && (
            <p className="m-0 rounded-lg border border-amber-400/40 bg-amber-500/10 px-2 py-1.5 text-amber-100 text-[0.75rem]">
              {state.error}
            </p>
          )}
          {state.status === 'ready' && (
            <>
              <p className="m-0 mb-2 text-content-muted text-[0.6875rem]">
                {d.count === 0
                  ? 'Nothing generated from this checkpoint yet — tick it and run from the board.'
                  : `${d.count} image${d.count > 1 ? 's' : ''}, newest first.`}
              </p>
              {/* Two columns at 400 px, three from `sm` — thumbnails that stay
                  big enough to compare on a phone. */}
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                {d.images.map((img) => (
                  <button key={img.id} type="button" onClick={() => setZoom(img)}
                    title={`Seed ${img.seed ?? '—'} · strength ${img.strength}`}
                    className="relative aspect-square overflow-hidden rounded-md border border-border hover:border-indigo-400/60">
                    <img src={img.url} alt={`Generated at step ${target.step}`}
                      loading="lazy" className="h-full w-full object-cover" />
                    {img.rating === 1 && (
                      <span aria-hidden className="absolute right-0.5 top-0.5 text-[0.625rem]">👍</span>
                    )}
                    {img.rating === -1 && (
                      <span aria-hidden className="absolute right-0.5 top-0.5 text-[0.625rem]">👎</span>
                    )}
                  </button>
                ))}
              </div>
              {d.unlinked > 0 && (
                <p className="m-0 mt-3 border-t border-border pt-2 text-content-subtle text-[0.625rem]">
                  {d.unlinked} older test image{d.unlinked > 1 ? 's' : ''} could not be traced back
                  to a checkpoint (generated before the link was recorded, and the file name
                  says nothing certain). They are kept, just not shown under a node —
                  they are in the Test Studio.
                </p>
              )}
            </>
          )}
        </div>
      </aside>

      {zoom && (
        <div role="dialog" aria-label="Generated image"
          onClick={() => setZoom(null)}
          className="fixed inset-0 z-[60] flex flex-col items-center justify-center gap-2 bg-black/80 p-3">
          <img src={zoom.url} alt={`Generated at step ${target.step}`}
            className="max-h-[80vh] max-w-full rounded-lg object-contain" />
          <p className="m-0 max-w-full break-words text-center text-white/80 text-[0.6875rem]">
            seed {zoom.seed ?? '—'} · strength {zoom.strength}
            {zoom.prompt ? ` · ${zoom.prompt}` : ''}
          </p>
        </div>
      )}
    </>
  );
}
