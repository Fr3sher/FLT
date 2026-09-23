import { useEffect, useRef, useState } from 'react';
import { Check, Image, X } from 'lucide-react';
import { apiFetch } from '@lds/plugin-sdk';
import { HelpBadge } from '@lds/plugin-sdk';
import { defaultLibrarySelection, isVideoItem, libraryItemKey, librarySelectionError, librarySelectionKey, librarySources, referenceInfoUrl } from './referenceLibrary';
import useReferenceLibrary from './useReferenceLibrary';

const BUTTON = 'min-h-10 rounded-md border border-border px-3 py-2 text-xs text-content-muted hover:text-content disabled:opacity-40 lg:min-h-0';
const INPUT = 'min-h-10 w-full min-w-0 rounded-md border border-border bg-app px-2 py-2 text-xs text-content lg:min-h-0';
const labels = { image: 'images', video: 'videos', audio: 'audio' };

export default function ReferenceLibraryPicker({ kind, limit, heldKeys = [], disabled, onAdd, onClose, targetLabel }) {
  const availableSources = librarySources(kind);
  const [source, setSource] = useState(availableSources[0].id);
  const [collection, setCollection] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState([]);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const selections = useRef([]);
  const probes = useRef(new Map());
  const mounted = useRef(true);
  const addingRef = useRef(false);
  const feed = useReferenceLibrary({ kind, source, collection, query });
  useEffect(() => {
    mounted.current = true;
    const activeProbes = probes.current;
    return () => { mounted.current = false; activeProbes.forEach((p) => p.abort()); activeProbes.clear(); };
  }, []);
  const replace = (next) => { selections.current = next; setSelected(next); };
  const patch = (key, update) => replace(selections.current.map((s) => libraryItemKey(s.item) === key ? { ...s, ...update } : s));
  const forget = (key) => {
    probes.current.get(key)?.abort(); probes.current.delete(key);
    replace(selections.current.filter((s) => libraryItemKey(s.item) !== key));
  };
  const toggle = async (item) => {
    if (disabled || addingRef.current) return;
    const key = libraryItemKey(item);
    if (selections.current.some((s) => libraryItemKey(s.item) === key)) { forget(key); return; }
    if (selections.current.length >= limit) { setNotice(`There is room for ${limit} more ${labels[kind]}. Remove a selection first.`); return; }
    setNotice('');
    replace([...selections.current, defaultLibrarySelection(item, kind)]);
    if (kind === 'image') return;
    const controller = new AbortController();
    probes.current.set(key, controller);
    try {
      const info = await apiFetch(referenceInfoUrl(item.source), { signal: controller.signal, background: true });
      if (!mounted.current || probes.current.get(key) !== controller) return;
      const duration = Number(info.duration);
      patch(key, { item: { ...item, ...info }, duration: String(Math.min(15, duration > 0 ? duration : 15)), pending: false });
    } catch (e) {
      if (mounted.current && probes.current.get(key) === controller) patch(key, { pending: false, error: e?.message || 'Could not read this clip. Select it again to retry.' });
    } finally { if (probes.current.get(key) === controller) probes.current.delete(key); }
  };
  const add = async () => {
    if (addingRef.current || disabled || !selected.length || selected.length > limit || selected.some((s) => librarySelectionError(kind, s, heldKeys))) return;
    addingRef.current = true; setAdding(true); setNotice('');
    try {
      const added = await onAdd(selected);
      if (!mounted.current) return;
      const keys = new Set(added || []);
      replace(selections.current.filter((s) => !keys.has(librarySelectionKey(kind, s))));
      setNotice(keys.size ? `${keys.size} ${keys.size === 1 ? 'item added' : 'items added'}. You can choose more.` : 'Nothing was added. Check the preparation message and try again.');
    } catch (e) { if (mounted.current) setNotice(e?.message || 'Could not add these items.'); }
    finally { addingRef.current = false; if (mounted.current) setAdding(false); }
  };
  const locked = disabled || adding;
  const invalid = selected.some((s) => librarySelectionError(kind, s, heldKeys));
  const sources = feed.sources.length ? feed.sources.filter((s) => availableSources.some((a) => a.id === s.id)) : availableSources;

  return (
    <section data-probe-panel="reference-library" className="flex min-w-0 flex-col gap-3 rounded-lg border border-primary/30 bg-app p-3" aria-label={`${targetLabel || labels[kind]} library`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-semibold text-content">Choose {targetLabel || labels[kind]} from the library</h3>
        <HelpBadge topic="video-reference-library" />
        <button type="button" className={`${BUTTON} ml-auto`} disabled={adding} onClick={onClose} aria-label="Close reference library"><X className="h-4 w-4" /></button>
      </div>
      <fieldset disabled={locked} className="grid min-w-0 gap-2 sm:grid-cols-2">
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Library source
          <select aria-label="Library source" className={INPUT} value={source} onChange={(e) => { setSource(e.target.value); setCollection(''); }}>
            {sources.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Collection
          <select aria-label="Library collection" className={INPUT} value={collection} onChange={(e) => setCollection(e.target.value)} disabled={!feed.collections.length}>
            <option value="">All collections</option>
            {feed.collections.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted sm:col-span-2">Search
          <input type="search" aria-label="Search library" placeholder="Search names…" value={query} onChange={(e) => setQuery(e.target.value)} className={INPUT} />
        </label>
      </fieldset>
      {feed.error && <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-red-400">{feed.error}<button type="button" className={BUTTON} onClick={feed.retry}>Retry library</button></div>}
      <div className="grid max-h-72 min-w-0 grid-cols-2 gap-2 overflow-y-auto sm:grid-cols-3" aria-label="Library items" aria-busy={feed.loading}>
        {feed.items.map((item) => {
          const key = libraryItemKey(item);
          const checked = selected.some((s) => libraryItemKey(s.item) === key);
          return <button type="button" key={key} aria-label={`Select ${item.label}`} aria-pressed={checked}
            disabled={locked || (!checked && selected.length >= limit)} onClick={() => toggle(item)}
            className={`relative flex min-w-0 flex-col overflow-hidden rounded-md border text-left disabled:opacity-40 ${checked ? 'border-primary bg-primary/10' : 'border-border bg-surface hover:border-primary/50'}`}>
            {item.preview_url ? <img src={item.preview_url} alt="" loading="lazy" className="h-24 w-full object-contain" /> : <Image aria-hidden="true" className="mx-auto h-24 w-8 text-content-subtle" />}
            {checked && <Check aria-hidden="true" className="absolute right-1 top-1 h-5 w-5 rounded bg-primary text-gray-950" />}
            <span className="line-clamp-2 min-h-10 w-full break-words px-2 py-1 text-xs text-content" title={item.label}>{item.label}</span>
          </button>;
        })}
      </div>
      {feed.loading ? <p role="status" className="text-xs text-content-muted">Loading library…</p> : !feed.items.length && !feed.error && <p className="text-xs text-content-muted">No {labels[kind]} found in this library. Try another source or search.</p>}
      {feed.hasMore && <button type="button" className={BUTTON} disabled={feed.loading || locked} onClick={feed.more}>Load more</button>}
      {selected.length > 0 && <fieldset disabled={locked} className="min-w-0 space-y-2">
        <legend className="mb-2 text-xs font-semibold text-content">Selected · {selected.length}{Number.isFinite(limit) ? `/${limit}` : ''}</legend>
        {selected.map((selection) => {
          const { item } = selection;
          const key = libraryItemKey(item);
          const error = librarySelectionError(kind, selection, heldKeys);
          return <article key={key} className="min-w-0 space-y-2 rounded-md border border-border bg-surface p-2">
            <div className="flex min-w-0 items-center gap-2"><span className="min-w-0 flex-1 break-words text-xs text-content">{item.label}</span><button type="button" className={BUTTON} aria-label={`Deselect ${item.label}`} onClick={() => forget(key)}><X className="h-3.5 w-3.5" /></button></div>
            {kind === 'image' && isVideoItem(item) && <>
              <label className="flex flex-col gap-1 text-xs text-content-muted">Frame to use
                <select aria-label={`Frame from ${item.label}`} value={selection.frame} onChange={(e) => patch(key, { frame: e.target.value })} className={INPUT}><option value="first">First frame</option><option value="last">Last frame</option></select>
              </label>
              <p className="text-[0.6875rem] text-content-subtle">The thumbnail is the clip poster. The chosen frame is extracted when you add it.</p>
            </>}
            {kind !== 'image' && <>
              <p className="text-xs text-content-muted">{Number(item.duration) > 0 ? `Clip length: ${Number(item.duration).toFixed(2)} s. ` : ''}{kind === 'audio' ? 'Extract sound from this interval.' : 'Use the video in this interval.'} Times start at the beginning of this clip.</p>
              <div className="grid min-w-0 grid-cols-2 gap-2">
                <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Start · seconds<input type="number" aria-label={`Start seconds for ${item.label}`} min="0" step="0.1" value={selection.start} disabled={selection.pending} onChange={(e) => patch(key, { start: e.target.value })} className={INPUT} /></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Duration · seconds<input type="number" aria-label={`Duration seconds for ${item.label}`} min={kind === 'video' ? 2 : 0.2} max="15" step="0.1" value={selection.duration} disabled={selection.pending} onChange={(e) => patch(key, { duration: e.target.value })} className={INPUT} /></label>
              </div>
              {kind === 'video' && <label className="flex min-h-10 items-center gap-2 text-xs text-content-muted lg:min-h-0"><input type="checkbox" checked={selection.includeAudio} disabled={selection.pending || item.has_audio === false} onChange={(e) => patch(key, { includeAudio: e.target.checked })} />{item.has_audio === false ? 'This clip has no audio track' : 'Also include this excerpt’s sound'}</label>}
            </>}
            {error && <p role="status" className="text-xs text-content-muted">{error}</p>}
          </article>;
        })}
      </fieldset>}
      {selected.length > 0 && <button type="button" className="min-h-10 w-full rounded-md bg-primary px-3 py-2 text-xs font-semibold text-gray-950 disabled:opacity-40 lg:min-h-0" disabled={locked || selected.length > limit || invalid} onClick={add}>{adding ? 'Preparing selection…' : `Add selected (${selected.length})`}</button>}
      <p role="status" aria-live="polite" className="min-w-0 text-xs text-content-muted">{notice || (selected.length ? '' : Number.isFinite(limit) ? `Select up to ${limit} ${labels[kind]} to add.` : `Select ${labels[kind]} to add.`)}</p>
    </section>
  );
}
