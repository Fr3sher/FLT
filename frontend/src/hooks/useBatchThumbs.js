/* useBatchThumbs — prefetch a grid's thumbnails as BATCHES so a high-RTT link
 * pays one round trip per batch, not one per tile. See batchThumbs.js.
 *
 * `keys` is the opaque list of things to draw (image ids / filenames / urls).
 * `buildRequest(batchKeys)` returns `{ url, body }` (body = JSON string) for the
 * matching batch endpoint. Fetched in order, `concurrency` at a time; every
 * fetched blob is retained as `{ key -> blobUrl }` and the caller renders a
 * placeholder until a key's blob lands (the single <img> remains the fallback
 * for keys the batch response omitted).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { decodeBatchThumbs } from '../utils/batchThumbs';

const DEFAULTS = { batchSize: 16, concurrency: 2 };

export default function useBatchThumbs(keys, buildRequest, opts = {}) {
  const { batchSize, concurrency, rev } = { ...DEFAULTS, ...opts };
  const [blobMap, setBlobMap] = useState(() => new Map());
  const fetched = useRef(new Set());
  const buildRef = useRef(buildRequest);
  buildRef.current = buildRequest;

  const cacheKey = keys.join('\u0000');

  useEffect(() => {
    // A changed page (or a rotation that must re-materialise) starts a fresh
    // batch pass: drop the remember-what-we-asked set so changed bytes refetch.
    fetched.current.clear();
    const toFetch = keys.filter((k) => !fetched.current.has(k));
    if (!toFetch.length) return;
    const batches = [];
    for (let i = 0; i < toFetch.length; i += batchSize) {
      batches.push(toFetch.slice(i, i + batchSize));
    }
    let bi = 0;
    let active = 0;
    let cancelled = false;

    const pump = () => {
      if (cancelled) return;
      while (bi < batches.length && active < concurrency) {
        const batch = batches[bi++];
        batch.forEach((k) => fetched.current.add(k));
        active += 1;
        const { url, body } = buildRef.current(batch);
        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
          .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error('batch'))))
          .then((buf) => {
            const got = decodeBatchThumbs(buf);
            const next = new Map();
            Object.keys(got).forEach((posStr) => {
              const key = batch[Number(posStr)];
              if (key != null) next.set(key, URL.createObjectURL(got[posStr]));
            });
            if (next.size) {
              setBlobMap((prev) => {
                const m = new Map(prev);
                next.forEach((v, k) => m.set(k, v));
                return m;
              });
            }
          })
          .catch(() => { /* leave that key for the on-demand <img> fallback */ })
          .finally(() => { active -= 1; pump(); });
      }
    };
    pump();
    return () => { cancelled = true; };
  }, [cacheKey, rev, batchSize, concurrency]);

  const getBlobUrl = useCallback((key) => blobMap.get(key) || null, [blobMap]);
  return { getBlobUrl };
}
