export const LIBRARY_SOURCES = [
  { id: 'bank', label: 'Image bank' }, { id: 'gallery', label: 'Gallery' },
  { id: 'dataset', label: 'Image datasets' }, { id: 'video_bank', label: 'Video bank' },
  { id: 'video_dataset', label: 'Video datasets' }, { id: 'studio', label: 'Rendered clips' },
];
export const isVideoSource = (source) => ['video_bank', 'video_dataset', 'studio'].includes(source?.type || source);
export const isVideoItem = (item) => item.media_kind ? item.media_kind === 'video' : isVideoSource(item.source);
export const librarySources = (kind) => LIBRARY_SOURCES.filter((s) => kind === 'image' || isVideoSource(s.id));

export function referenceLibraryUrl({ kind, source, collection = '', query = '', offset = 0 }) {
  const q = new URLSearchParams({ kind, source, offset: String(offset), limit: '40' });
  if (collection !== '') q.set('collection_id', String(collection));
  if (query.trim()) q.set('q', query.trim());
  return `/api/video-studio/reference-library?${q}`;
}
export function referenceInfoUrl(source) {
  const q = new URLSearchParams({ type: source.type, id: String(source.id) });
  if (source.collection_id != null) q.set('collection_id', String(source.collection_id));
  return `/api/video-studio/reference-library/info?${q}`;
}
export const libraryItemKey = (item) => JSON.stringify([item.source.type, String(item.source.collection_id ?? ''), String(item.source.id)]);
const selectionFrame = (selection) => isVideoItem(selection.item) ? selection.frame || 'first' : 'first';
export function librarySelectionKey(kind, selection) {
  return `library:${JSON.stringify([kind, libraryItemKey(selection.item),
    ...(kind === 'image' ? [selectionFrame(selection)] : [Number(selection.start), Number(selection.duration), !!selection.includeAudio])])}`;
}
export function referenceLibraryKey(reference) {
  if (!reference.library_source) return reference.key || reference.name;
  return librarySelectionKey(reference.kind, { item: { source: reference.library_source }, frame: reference.frame,
    start: reference.start_seconds, duration: reference.duration_seconds, includeAudio: reference.include_audio });
}
export function defaultLibrarySelection(item, kind) {
  const duration = Number(item.duration);
  return { item, frame: 'first', start: '0', duration: String(Math.min(15, duration > 0 ? duration : 15)),
    includeAudio: false, pending: kind !== 'image', error: '' };
}
export function librarySelectionError(kind, selection, held = []) {
  if (selection.pending) return 'Reading clip duration and sound…';
  if (selection.error) return selection.error;
  if (kind !== 'image') {
    const min = kind === 'video' ? 2 : 0.2;
    const start = Number(selection.start), duration = Number(selection.duration);
    const total = Number(selection.item.duration);
    if (kind === 'audio' && selection.item.has_audio === false) return 'This clip has no audio track.';
    if (!Number.isFinite(total) || total <= 0) return 'The clip duration could not be read.';
    if (String(selection.start).trim() === '' || !Number.isFinite(start) || start < 0) return 'Enter a start time of 0 seconds or later.';
    if (String(selection.duration).trim() === '' || !Number.isFinite(duration) || duration < min || duration > 15) return `Choose ${min}–15 seconds.`;
    if (start + duration > total + 0.001) return 'The excerpt extends past the end of this clip.';
  }
  if (held.includes(librarySelectionKey(kind, selection))) return 'This reference is already added. Choose another frame or excerpt.';
  return '';
}
export function librarySelectionBody(kind, selection) {
  return { kind, library_source: selection.item.source,
    ...(kind === 'image' ? { frame: selectionFrame(selection) }
      : { start_seconds: Number(selection.start), duration_seconds: Number(selection.duration),
        ...(kind === 'video' ? { include_audio: !!selection.includeAudio } : {}) }) };
}

export function mergeLibraryItems(before, after) {
  const seen = new Set();
  return [...before, ...after].filter((item) => {
    const key = item.key || libraryItemKey(item);
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
}

/** One request generation owns a feed. A source/search change cancels the old
 * page, including a late Load more, without letting its error replace the new UI. */
export function createReferenceLibraryFeed(fetchPage, onChange) {
  let state = { sources: [], collections: [], items: [], loading: false, error: '', hasMore: false, nextOffset: 0 };
  let params = {}, revision = 0, alive = true, controller;
  const emit = (patch) => { state = { ...state, ...patch }; if (alive) onChange(state); };
  const request = async (offset, append) => {
    const mine = ++revision;
    controller?.abort(); controller = new AbortController();
    emit({ loading: true, error: '', ...(append ? {} : { items: [], collections: [], hasMore: false, nextOffset: 0 }) });
    try {
      const data = await fetchPage(referenceLibraryUrl({ ...params, offset }), { signal: controller.signal, background: true });
      if (!alive || mine !== revision) return;
      const next = Number(data.next_offset);
      emit({ loading: false, sources: data.sources || [], collections: data.collections || [],
        items: mergeLibraryItems(append ? state.items : [], data.items || []),
        hasMore: !!data.has_more && Number.isFinite(next) && next > offset, nextOffset: next || 0 });
    } catch (error) {
      if (alive && mine === revision) emit({ loading: false, error: error?.message || 'Could not read this library.' });
    }
  };
  return {
    query(next) { if (!alive) return; params = { ...next }; return request(0, false); },
    more() { if (alive && !state.loading && state.hasMore) return request(state.nextOffset, true); },
    dispose() { alive = false; revision += 1; controller?.abort(); },
  };
}
