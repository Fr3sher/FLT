import { useCallback, useEffect, useState } from 'react';
import { apiFetch, postJson } from '../../api/fetchClient';
import {
  allGalleryImageIds, galleryDeleteConfirmation, galleryDeleteSummary,
  pruneGallerySelection, toggleGalleryImage,
} from '../../utils/gallerySelection';

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
   many there are. An incomplete history that says so beats a tidy one that lies.

   🗑 And it deletes. A checkpoint accumulates dozens of renders and most are
   misses; a gallery that can only show them makes the user leave the board to
   clean up. The delete is REAL (the row is the Test Studio's own cell — see
   galleryDeleteConfirmation for the sentences that say so before the click) and
   the file goes to the recycle bin / the app Trash rather than being destroyed.

   Deletion is deliberately UNREACHABLE by accident: it needs Select mode, then a
   pick, then a confirmation. Tapping a tile while scrolling a phone grid can
   never delete anything — outside Select mode a tap only zooms. */
export default function CheckpointGalleryPanel({ target, onClose, onDeleted }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: null });
  const [zoom, setZoom] = useState(null);
  const [picking, setPicking] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => {
    if (!target) return Promise.resolve();
    return apiFetch(`/api/train/checkpoint/${target.recordId}/${target.step}/images`)
      .then((d) => {
        setState({ status: 'ready', data: d, error: null });
        // A refresh that no longer lists an image must not leave it armed.
        setSelected((cur) => pruneGallerySelection(cur, d.images));
      })
      .catch((e) => {
        setState({
          status: 'error', data: null,
          error: e?.message || 'Could not load this checkpoint’s images',
        });
      });
  }, [target?.recordId, target?.step]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!target) return undefined;
    setState({ status: 'loading', data: null, error: null });
    setPicking(false);
    setSelected(new Set());
    setConfirming(false);
    setNotice(null);
    load();
    return undefined;
  }, [target?.recordId, target?.step]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!zoom) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setZoom(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoom]);

  const runDelete = useCallback(async () => {
    if (!target || busy) return;
    const ids = [...selected];
    setBusy(true);
    try {
      const res = await postJson(
        `/api/train/checkpoint/${target.recordId}/${target.step}/images/delete`,
        { image_ids: ids });
      setNotice({ kind: 'ok', text: galleryDeleteSummary(res) });
      setConfirming(false);
      setSelected(new Set());
      setPicking(false);
      await load();
      // The pills outside carry a results COUNT and a thumbnail: without this
      // the board keeps advertising images that no longer exist.
      onDeleted?.(res.dataset_ids || []);
    } catch (e) {
      setNotice({ kind: 'error', text: e?.message || 'Could not delete these images' });
    } finally {
      setBusy(false);
    }
  }, [target, selected, busy, load, onDeleted]);

  if (!target) return null;
  const d = state.data;
  const images = d?.images || [];
  const confirmation = galleryDeleteConfirmation(selected.size, d?.delete_mode);

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
          {/* The gate into deletion. Absent while there is nothing to delete, so
              an empty gallery carries no destructive control at all. */}
          {state.status === 'ready' && images.length > 0 && (
            <button type="button" data-testid="gallery-select-toggle"
              onClick={() => { setPicking((v) => !v); setSelected(new Set()); setNotice(null); }}
              aria-pressed={picking}
              title={picking ? 'Leave selection mode' : 'Select images to delete'}
              className={`shrink-0 rounded-md border px-2 py-1.5 text-[0.6875rem] ${picking
                ? 'border-indigo-400/60 bg-indigo-500/15 text-indigo-100'
                : 'border-border text-content-muted hover:text-content'}`}>
              {picking ? 'Done' : 'Select'}
            </button>
          )}
          <button type="button" onClick={onClose} aria-label="Close"
            className="shrink-0 px-1 py-1 text-content-subtle hover:text-content">✕</button>
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
          {notice && (
            <p className={`m-0 mb-2 rounded-lg border px-2 py-1.5 text-[0.6875rem] ${
              notice.kind === 'error'
                ? 'border-amber-400/40 bg-amber-500/10 text-amber-100'
                : 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100'}`}>
              {notice.text}
            </p>
          )}
          {state.status === 'ready' && (
            <>
              <p className="m-0 mb-2 text-content-muted text-[0.6875rem]">
                {d.count === 0
                  ? 'Nothing generated from this checkpoint yet — tick it and run from the board.'
                  : picking
                    ? `Tap the misses, then 🗑 Delete. ${d.count} image${d.count > 1 ? 's' : ''} here.`
                    : `${d.count} image${d.count > 1 ? 's' : ''}, newest first.`}
              </p>
              {/* Two columns at 400 px, three from `sm` — thumbnails that stay
                  big enough to compare on a phone. */}
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                {images.map((img) => {
                  const isPicked = selected.has(img.id);
                  return (
                    <button key={img.id} type="button"
                      data-testid={picking ? 'gallery-pick' : 'gallery-zoom'}
                      onClick={() => (picking
                        ? setSelected((cur) => toggleGalleryImage(cur, img.id))
                        : setZoom(img))}
                      aria-pressed={picking ? isPicked : undefined}
                      title={picking
                        ? (isPicked ? 'Selected — tap to unselect' : 'Tap to select')
                        : `Seed ${img.seed ?? '—'} · strength ${img.strength}`}
                      className={`relative aspect-square overflow-hidden rounded-md border ${isPicked
                        ? 'border-rose-400 ring-2 ring-rose-400/70'
                        : 'border-border hover:border-indigo-400/60'}`}>
                      <img src={img.url} alt={`Generated at step ${target.step}`}
                        loading="lazy"
                        className={`h-full w-full object-cover ${isPicked ? 'opacity-60' : ''}`} />
                      {picking && (
                        // A 24-px tick, not a hairline checkbox: the target has to
                        // be hittable with a thumb on a 400-px grid.
                        <span aria-hidden
                          className={`absolute left-1 top-1 flex h-6 w-6 items-center justify-center rounded-full border text-[0.75rem] ${isPicked
                            ? 'border-rose-300 bg-rose-500 text-white'
                            : 'border-white/60 bg-black/50 text-transparent'}`}>✓</span>
                      )}
                      {img.rating === 1 && (
                        <span aria-hidden className="absolute right-0.5 top-0.5 text-[0.625rem]">👍</span>
                      )}
                      {img.rating === -1 && (
                        <span aria-hidden className="absolute right-0.5 top-0.5 text-[0.625rem]">👎</span>
                      )}
                    </button>
                  );
                })}
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

        {/* The action bar only exists in Select mode, pinned so it stays reachable
            with a thumb however far the grid has been scrolled. */}
        {picking && state.status === 'ready' && (
          <div data-testid="gallery-action-bar"
            className="flex shrink-0 flex-wrap items-center gap-2 border-t border-border bg-surface-overlay px-3 py-2">
            <span className="text-content-muted text-[0.6875rem]">{selected.size} selected</span>
            <button type="button"
              onClick={() => setSelected(selected.size === images.length
                ? new Set() : allGalleryImageIds(images))}
              className="rounded-md border border-border px-2 py-1.5 text-content-muted text-[0.6875rem] hover:text-content">
              {selected.size === images.length ? 'Clear' : 'Select all'}
            </button>
            <button type="button" data-testid="gallery-delete"
              disabled={selected.size === 0 || busy}
              onClick={() => setConfirming(true)}
              className="ml-auto rounded-md border border-rose-500/50 px-3 py-1.5 text-[0.75rem] text-rose-300 disabled:opacity-40 hover:bg-rose-500/10">
              🗑 Delete{selected.size ? ` (${selected.size})` : ''}
            </button>
          </div>
        )}
      </aside>

      {/* The confirmation. Both consequences are stated BEFORE the button arms:
          the images leave the Test Studio too, and where the files land. */}
      {confirming && (
        <div role="dialog" aria-modal="true" aria-label="Confirm deletion"
          data-testid="gallery-confirm"
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-3">
          <div className="w-full max-w-sm rounded-xl border border-border bg-surface-overlay p-4 shadow-xl">
            <h4 className="m-0 mb-2 text-sm font-semibold text-content">{confirmation.title}</h4>
            <ul className="m-0 mb-3 list-disc space-y-1 pl-4 text-content-muted text-[0.75rem]">
              {confirmation.lines.map((line) => <li key={line}>{line}</li>)}
            </ul>
            {confirmation.destructive && (
              <p className="m-0 mb-3 rounded-lg border border-rose-400/40 bg-rose-500/10 px-2 py-1.5 text-rose-100 text-[0.6875rem]">
                This cannot be undone.
              </p>
            )}
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" autoFocus onClick={() => setConfirming(false)}
                className="rounded-md border border-border px-3 py-2 text-content-muted text-[0.75rem] hover:text-content">
                Cancel
              </button>
              <button type="button" data-testid="gallery-confirm-delete"
                disabled={busy} onClick={runDelete}
                className="rounded-md border border-rose-500/60 bg-rose-500/15 px-3 py-2 text-[0.75rem] text-rose-100 disabled:opacity-40 hover:bg-rose-500/25">
                {busy ? 'Deleting…' : `Delete ${selected.size}`}
              </button>
            </div>
          </div>
        </div>
      )}

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
