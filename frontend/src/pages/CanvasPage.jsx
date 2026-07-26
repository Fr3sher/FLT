import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '../api/fetchClient';
import {
  readSelection, resolveSelection, toggleSelection, writeSelection,
} from '../utils/canvasSelection';
import CanvasDatasetFilter from '../components/canvas/CanvasDatasetFilter';
import LineageCanvas from '../components/canvas/LineageCanvas';
import { HelpBadge } from '../help/HelpMode';

/* ◉ LoRA Canvas — every dataset's training genealogy on one board.

   Until now a lineage graph was locked inside a single run's card: one dataset
   at a time, in a fixed frame. This page promotes it. Same trees, same cards,
   same edges — but all of them on one surface you can zoom and pan, with a
   filter to decide which datasets are on it.

   Loading is deliberately in TWO steps. The index (which datasets have runs) is
   a couple of grouped queries and arrives instantly, so the filter and the frame
   are usable straight away; each dataset's genealogy — which scans that run's
   saves on disk — is then fetched on its own and its lane fills in when it
   lands. One request for the whole library would have meant an empty screen for
   as long as the slowest disk scan took.

   Fetches are capped to a few at a time. A library of thirty trained datasets
   firing thirty concurrent disk-scanning requests would stall the very server
   that also has to answer whatever training or captioning is running. */

const MAX_PARALLEL_FETCHES = 3;

export default function CanvasPage() {
  const [index, setIndex] = useState({ status: 'loading', datasets: [], error: null });
  const [stored, setStored] = useState(() => readSelection(
    typeof localStorage !== 'undefined' ? localStorage : null));
  // dataset_id -> { status: 'loading'|'ready'|'error', tree, error }
  const [trees, setTrees] = useState({});
  const inflight = useRef(new Set());

  useEffect(() => {
    let alive = true;
    apiFetch('/api/train/canvas/datasets')
      .then((d) => { if (alive) setIndex({ status: 'ready', datasets: d?.datasets || [], error: null }); })
      .catch((e) => { if (alive) setIndex({ status: 'error', datasets: [], error: e?.message || 'Could not load your datasets' }); });
    return () => { alive = false; };
  }, []);

  const availableIds = useMemo(() => index.datasets.map((d) => d.id), [index.datasets]);
  const selected = useMemo(() => resolveSelection(availableIds, stored), [availableIds, stored]);

  const persist = useCallback((ids) => {
    setStored(ids);
    writeSelection(typeof localStorage !== 'undefined' ? localStorage : null, ids);
  }, []);

  const onToggle = useCallback((id) => {
    persist(toggleSelection(selected, id, availableIds));
  }, [persist, selected, availableIds]);

  // Fetch the genealogy of every selected dataset that has none yet, a few at a
  // time. A dataset unticked and re-ticked keeps its cached tree — the board must
  // not re-scan the disk for a filter click.
  useEffect(() => {
    const missing = selected.filter((id) => !trees[id] && !inflight.current.has(id));
    if (!missing.length) return;
    const room = MAX_PARALLEL_FETCHES - inflight.current.size;
    if (room <= 0) return;
    for (const id of missing.slice(0, room)) {
      inflight.current.add(id);
      setTrees((t) => ({ ...t, [id]: { status: 'loading', tree: null, error: null } }));
      apiFetch(`/api/dataset/${id}/train/lineage`)
        .then((tree) => setTrees((t) => ({ ...t, [id]: { status: 'ready', tree, error: null } })))
        .catch((e) => setTrees((t) => ({ ...t,
          [id]: { status: 'error', tree: null, error: e?.message || 'Could not load this lineage' } })))
        .finally(() => {
          inflight.current.delete(id);
          // Nudge the effect so the next batch starts.
          setTrees((t) => ({ ...t }));
        });
    }
  }, [selected, trees]);

  const entries = useMemo(() => selected.map((id) => {
    const row = index.datasets.find((d) => d.id === id);
    const state = trees[id];
    return {
      datasetId: id,
      name: row?.name || `Dataset ${id}`,
      runs: row?.runs || 0,
      families: row?.families || [],
      status: state?.status || 'loading',
      error: state?.error || null,
      // The RAW tree, not a laid-out graph: the canvas has to be able to lay it
      // out again when a run is removed from the board (see LineageCanvas).
      tree: state?.tree || null,
    };
  }), [selected, index.datasets, trees]);

  return (
    <div>
      <header className="mb-3">
        <h1 className="flex items-center gap-2 text-lg font-semibold text-content">
          <span aria-hidden>◉</span> LoRA Canvas
          <span className="px-1.5 py-0.5 rounded border border-amber-400/50 bg-amber-500/10 text-amber-300 text-[0.625rem] font-semibold uppercase tracking-wide">Beta</span>
          <HelpBadge topic="page-canvas" />
        </h1>
        <p className="mt-1 text-content-muted text-[0.75rem]">
          Every training run you have made, on one board: each dataset gets a lane, each run a card,
          and a continuation is joined to the exact checkpoint it resumed from.
        </p>
      </header>

      {index.status === 'error' && (
        <p className="mb-3 rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-amber-100 text-[0.75rem]">
          {index.error}
        </p>
      )}

      <CanvasDatasetFilter
        datasets={index.datasets}
        selected={selected}
        onToggle={onToggle}
        onAll={() => persist(availableIds)}
        onNone={() => persist([])} />

      {index.status === 'loading'
        ? <p className="text-content-subtle text-[0.75rem]">Loading your datasets…</p>
        : <LineageCanvas entries={entries} />}
    </div>
  );
}
