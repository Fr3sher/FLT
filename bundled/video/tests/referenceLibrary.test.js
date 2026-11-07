import assert from 'node:assert/strict';
import test from 'node:test';
import { createReferenceLibraryFeed, defaultLibrarySelection, isVideoItem, libraryItemKey, librarySelectionBody,
  librarySelectionError, librarySelectionKey, librarySources, referenceInfoUrl, referenceLibraryKey,
  referenceLibraryUrl } from '../frontend/studio/video/referenceLibrary.js';
import { readReferenceDraft, referenceDescriptors, referencePayload, writeReferenceDraft } from '../frontend/studio/video/videoReferences.js';

const item = { key: 'clip-1', label: 'Walk', duration: 22, has_audio: true,
  source: { type: 'video_bank', collection_id: 4, id: 12 } };
const selection = (patch = {}) => ({ ...defaultLibrarySelection(item, 'video'), pending: false, ...patch });
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const page = (items, next = 0, more = false) => ({ items, next_offset: next, has_more: more, sources: [], collections: [] });

test('images can come from all six libraries, audio and video only from clip libraries', () => {
  assert.deepEqual(librarySources('image').map((s) => s.id), ['bank', 'gallery', 'dataset', 'video_bank', 'video_dataset', 'studio']);
  for (const kind of ['video', 'audio']) assert.deepEqual(librarySources(kind).map((s) => s.id), ['video_bank', 'video_dataset', 'studio']);
});

test('frame availability follows the known media kind, with source fallback for legacy items', () => {
  const source = { type: 'video_dataset', collection_id: 7, id: 11 };
  assert.equal(isVideoItem({ source, media_kind: 'image' }), false);
  assert.equal(isVideoItem({ source, media_kind: 'video' }), true);
  assert.equal(isVideoItem({ source }), true);
  assert.equal(isVideoItem({ source: { type: 'bank', id: 1 } }), false);
});

test('library requests encode search and collection ids without changing their boundaries', () => {
  const url = new URL(referenceLibraryUrl({ kind: 'audio', source: 'video_bank', collection: 'one&two', query: '  walk & turn  ', offset: 40 }), 'https://example.test');
  assert.equal(url.searchParams.get('collection_id'), 'one&two');
  assert.equal(url.searchParams.get('q'), 'walk & turn');
  assert.equal(url.searchParams.get('offset'), '40'); assert.equal(url.searchParams.get('limit'), '40');
  assert.equal(new URL(referenceLibraryUrl({ kind: 'image', source: 'bank' }), 'https://example.test').searchParams.has('collection_id'), false);
  const info = new URL(referenceInfoUrl(item.source), 'https://example.test');
  assert.equal(info.searchParams.get('type'), 'video_bank'); assert.equal(info.searchParams.get('id'), '12');
  assert.equal(info.searchParams.get('collection_id'), '4');
});

test('clip selection waits for real metadata and chooses a bounded default excerpt', () => {
  const long = defaultLibrarySelection(item, 'video');
  assert.equal(long.duration, '15'); assert.equal(long.start, '0'); assert.equal(long.includeAudio, false);
  assert.match(librarySelectionError('video', long), /Reading clip/);
  assert.equal(defaultLibrarySelection({ ...item, duration: 3.5 }, 'audio').duration, '3.5');
  assert.equal(defaultLibrarySelection(item, 'image').pending, false);
});

test('excerpt validation rejects empty, nonfinite, short, long and out-of-clip intervals', () => {
  for (const patch of [{ start: '' }, { start: '-1' }, { start: 'NaN' }, { duration: '' }, { duration: 'Infinity' },
    { duration: '1.9' }, { duration: '15.1' }, { start: '8', duration: '15' }, { item: { ...item, duration: null } }]) {
    assert.ok(librarySelectionError('video', selection(patch)), JSON.stringify(patch));
  }
  assert.equal(librarySelectionError('video', selection({ start: '7', duration: '15' })), '');
  assert.equal(librarySelectionError('audio', selection({ duration: '0.2' })), '');
  assert.ok(librarySelectionError('audio', selection({ duration: '0.19' })));
  assert.match(librarySelectionError('audio', selection({ item: { ...item, has_audio: false } })), /no audio track/);
  assert.equal(librarySelectionError('video', selection({ item: { ...item, has_audio: false } })), '');
});

test('selection requests keep first and last extraction distinct from video and audio excerpts', () => {
  assert.deepEqual(librarySelectionBody('image', selection({ frame: 'last' })), { kind: 'image', library_source: item.source, frame: 'last' });
  assert.deepEqual(librarySelectionBody('video', selection({ start: '5.5', duration: '4', includeAudio: true })),
    { kind: 'video', library_source: item.source, start_seconds: 5.5, duration_seconds: 4, include_audio: true });
  assert.deepEqual(librarySelectionBody('audio', selection({ start: '3', duration: '2.4' })),
    { kind: 'audio', library_source: item.source, start_seconds: 3, duration_seconds: 2.4 });
});

test('deduplication identity includes source, collection, media kind, frame and excerpt', () => {
  const identities = [librarySelectionKey('image', selection()), librarySelectionKey('image', selection({ frame: 'last' })),
    librarySelectionKey('video', selection()), librarySelectionKey('audio', selection()),
    librarySelectionKey('video', selection({ start: '2' })), librarySelectionKey('video', selection({ duration: '4' })),
    librarySelectionKey('video', selection({ item: { ...item, source: { ...item.source, collection_id: 9 } } })),
    librarySelectionKey('video', selection({ item: { ...item, source: { ...item.source, type: 'studio' } } }))];
  assert.equal(new Set(identities).size, identities.length);
  assert.equal(libraryItemKey(item), libraryItemKey({ source: { type: 'video_bank', collection_id: '4', id: '12' } }));
  assert.match(librarySelectionError('video', selection(), [identities[2]]), /already added/);
  assert.equal(librarySelectionError('video', selection({ start: '2' }), [identities[2]]), '');
});

test('a still in a video dataset keeps one identity after canonical history and draft restoration', () => {
  const still = { label: 'still.png', media_kind: 'image', source: { type: 'video_dataset', collection_id: 7, id: 11 } };
  const first = defaultLibrarySelection(still, 'image');
  const last = { ...first, frame: 'last' };
  const restored = referenceDescriptors([{ kind: 'image', name: 'staged.png', library_source: still.source, frame: null }])[0];
  let saved;
  const storage = { setItem: (_key, value) => { saved = value; }, getItem: () => saved };
  writeReferenceDraft({ references: [restored] }, storage);
  const held = readReferenceDraft(storage).references.map(referenceLibraryKey);
  assert.equal(librarySelectionKey('image', last), librarySelectionKey('image', first));
  assert.equal(held[0], librarySelectionKey('image', last));
  assert.match(librarySelectionError('image', last, held), /already added/);
  assert.equal(librarySelectionBody('image', last).frame, 'first');
});

test('history provenance and draft round-trip recover the same selection identity without sending sources to Generate', () => {
  const original = { kind: 'video', name: 'staged.mp4', key: 'server-opaque-key', role: 'movement',
    library_source: item.source, source_label: item.label, start_seconds: 0, duration_seconds: 15, include_audio: false, duration: 15, has_audio: true };
  const restored = referenceDescriptors([original])[0];
  assert.equal(restored.key, librarySelectionKey('video', selection()));
  assert.equal(restored.source_label, 'Walk'); assert.deepEqual(restored.library_source, item.source);
  let saved;
  const storage = { setItem: (_k, value) => { saved = value; }, getItem: () => saved };
  writeReferenceDraft({ references: [restored] }, storage);
  assert.equal(referenceLibraryKey(readReferenceDraft(storage).references[0]), restored.key);
  assert.deepEqual(referencePayload([restored]), [{ kind: 'video', name: 'staged.mp4', role: 'movement', include_audio: false }]);
  assert.equal(referenceLibraryKey({ kind: 'image', name: 'frame.png', library_source: item.source, frame: 'last' }), librarySelectionKey('image', selection({ frame: 'last' })));
});

test('a late source response and its error cannot replace a newer library', async () => {
  const requests = [], changes = [];
  const feed = createReferenceLibraryFeed((url, options) => { const request = deferred(); requests.push({ ...request, url, options }); return request.promise; }, (s) => changes.push(s));
  const old = feed.query({ kind: 'image', source: 'bank' });
  const next = feed.query({ kind: 'image', source: 'gallery' });
  assert.equal(requests[0].options.signal.aborted, true);
  requests[1].resolve(page([{ ...item, key: 'new' }])); await next;
  requests[0].reject(new Error('old error')); await old;
  assert.equal(changes.at(-1).items[0].key, 'new'); assert.equal(changes.at(-1).error, '');
  const oldAgain = feed.query({ kind: 'image', source: 'bank' });
  const fresh = feed.query({ kind: 'image', source: 'studio' });
  requests[3].resolve(page([{ ...item, key: 'fresh' }])); await fresh;
  requests[2].resolve(page([{ ...item, key: 'old' }])); await oldAgain;
  assert.equal(changes.at(-1).items[0].key, 'fresh'); feed.dispose();
});

test('Load more is single-flight, deduplicates pages and cannot append to a changed search', async () => {
  const requests = []; let state;
  const feed = createReferenceLibraryFeed((url) => { const request = deferred(); requests.push({ ...request, url }); return request.promise; }, (s) => { state = s; });
  const first = feed.query({ kind: 'video', source: 'studio' }); requests[0].resolve(page([item], 40, true)); await first;
  const more = feed.more(); feed.more(); assert.equal(requests.length, 2);
  assert.equal(new URL(requests[1].url, 'https://example.test').searchParams.get('offset'), '40');
  requests[1].resolve(page([item, { ...item, key: 'second' }], 80, true)); await more;
  assert.equal(state.items.length, 2);
  const late = feed.more(); const search = feed.query({ kind: 'video', source: 'studio', query: 'new' });
  requests[3].resolve(page([{ ...item, key: 'searched' }])); await search;
  requests[2].resolve(page([{ ...item, key: 'stale-more' }], 120, true)); await late;
  assert.deepEqual(state.items.map((i) => i.key), ['searched']); feed.dispose();
});

test('disposal aborts reads and ignores late completion, including errors', async () => {
  let changes = 0, signal;
  const request = deferred();
  const feed = createReferenceLibraryFeed((_url, options) => { signal = options.signal; return request.promise; }, () => changes++);
  const pending = feed.query({ kind: 'image', source: 'bank' });
  feed.dispose(); const count = changes; request.reject(new Error('finished late')); await pending;
  assert.equal(signal.aborted, true); assert.equal(changes, count);
  await feed.query({ kind: 'image', source: 'gallery' }); assert.equal(changes, count);
});

test('failed pages preserve loaded items for retry, and non-advancing pagination stops', async () => {
  let count = 0, state;
  const feed = createReferenceLibraryFeed(async () => {
    count++; if (count === 1) return page([item], 40, true);
    if (count === 2) throw new Error('temporarily unavailable');
    return page([], 40, true);
  }, (s) => { state = s; });
  await feed.query({ kind: 'video', source: 'studio' }); await feed.more();
  assert.equal(state.items.length, 1); assert.equal(state.error, 'temporarily unavailable');
  await feed.more(); assert.equal(state.hasMore, false); assert.equal(state.error, '');
  feed.more(); assert.equal(count, 3); feed.dispose();
});
