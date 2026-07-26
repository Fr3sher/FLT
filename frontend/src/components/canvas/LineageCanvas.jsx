import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildLineageGraph, CARD_W } from '../../utils/lineageGraph';
import {
  LANE_HEADER_H, MAX_SCALE, MIN_SCALE,
  clampScale, clampView, fitView, initialView, panBy, pinchCenter, pinchDistance,
  stackLanes, viewTransform, zoomAt,
} from '../../utils/canvasLayout';
import { GraphCard, CheckpointPill } from '../dataset/lineageNodes';
import { LineageEdgeDefs, LineageEdges } from '../dataset/lineageEdges';
import { noteBadge, toggleDiffSelection } from '../dataset/lineageDetail.js';
import { removeRunFromTree } from '../../utils/runDeletable.js';
import LineageDetailPanel from '../dataset/LineageDetailPanel';
import LineageDiffPanel from '../dataset/LineageDiffPanel';

/* ◉ The LoRA Canvas surface — every selected dataset's genealogy on ONE board,
   with zoom and pan.

   It draws with the SAME card, pill and edge components as the graph embedded in
   a run's card (components/dataset/lineageNodes + lineageEdges); the geometry of
   each dataset's tree is still utils/lineageGraph.js. What is new here is only
   the surface: several trees stacked into lanes, and a viewport you can move.

   Slice 1 deliberately stops there. Nodes do not move yet (slice 2) and nothing
   generates from here yet (slice 3), so a checkpoint pill opens its run's
   inspector rather than pretending to offer actions it cannot perform — a dead
   click would be worse than no click. The in-card graph keeps every one of those
   actions until the canvas actually reaches parity.

   Gestures: wheel (or trackpad pinch, which arrives as ctrl+wheel) zooms around
   the pointer; dragging the background pans; two fingers pinch-zoom. Dragging a
   NODE is not a gesture yet, so the background drag is unambiguous — the touch
   long-press that will disambiguate it belongs to slice 2. */

const ZOOM_STEP = 1.25;

/** One dataset's title strip above its tree. Inside the zoomed world, so it
 *  scales with the board it labels — a lane whose name floated at a constant
 *  size would drift off its tree the moment you zoomed out. */
function LaneHeader({ lane }) {
  return (
    <div style={{ position: 'absolute', left: 0, top: lane.y, height: LANE_HEADER_H,
      width: Math.max(lane.width, CARD_W) }}
      className="flex items-center gap-2 overflow-hidden">
      <span className="truncate text-[0.8125rem] font-semibold text-content" title={lane.name}>
        {lane.name}
      </span>
      <span className="shrink-0 rounded-full border border-border bg-app/60 px-1.5 py-0.5 text-content-muted text-[0.5625rem] font-medium tabular-nums">
        {lane.runs} run{lane.runs === 1 ? '' : 's'}
      </span>
      {lane.status === 'loading' && (
        <span className="shrink-0 animate-pulse text-content-subtle text-[0.625rem]">loading…</span>
      )}
      {lane.status === 'error' && (
        <span className="shrink-0 text-amber-300 text-[0.625rem]" title={lane.error || ''}>
          could not load this dataset
        </span>
      )}
      {lane.status === 'ready' && !lane.height && (
        <span className="shrink-0 text-content-subtle text-[0.625rem]">no runs to draw</span>
      )}
    </div>
  );
}

/** One dataset's tree, drawn exactly as the in-card graph draws it. */
function LaneGraph({ lane, isLit, onHover, onNodeClick, diffRole, noteOf }) {
  const g = lane.graph;
  if (!g || !g.nodes.length) return null;
  return (
    <svg
      style={{ position: 'absolute', left: 0, top: lane.graphY }}
      className="lds-lgraph block overflow-visible"
      width={g.width} height={g.height}
      viewBox={`0 0 ${g.width} ${g.height}`}
      role="img"
      aria-label={`${lane.name}: lineage of ${g.nodes.length} run${g.nodes.length === 1 ? '' : 's'}`}>
      <LineageEdges edges={g.edges} isLit={isLit} />
      <g>
        {g.nodes.map((n) => (
          <foreignObject key={n.node.record_id}
            className="lds-gnode overflow-visible"
            x={n.x} y={n.y} width={CARD_W} height={n.cellH}
            onPointerEnter={() => onHover(n.node.record_id)}
            onPointerLeave={() => onHover(null, n.node.record_id)}>
            <div style={{ position: 'relative', width: CARD_W, height: n.cellH }}>
              <GraphCard node={noteOf(n.node)} lit={isLit(n.node.record_id)}
                annotated={noteBadge(noteOf(n.node))}
                compareRole={diffRole(n.node.record_id)}
                onSelect={onNodeClick} />
              {n.checkpoints.map((p) => (
                <CheckpointPill key={`${p.step}-${p.filename ?? p.x}`}
                  pill={p} offX={p.x - n.x} offY={p.y - n.y}
                  preview={p.preview_status || p.preview_url
                    ? { status: p.preview_status, url: p.preview_url } : null}
                  onOpen={() => onNodeClick(n.node, null)} />
              ))}
            </div>
          </foreignObject>
        ))}
      </g>
    </svg>
  );
}

export default function LineageCanvas({ entries }) {
  const frameRef = useRef(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [view, setView] = useState({ scale: 1, tx: 0, ty: 0 });
  const [hoverId, setHoverId] = useState(null);
  const [openNode, setOpenNode] = useState(null);
  const [selectedForDiff, setSelectedForDiff] = useState([]);
  const [noteEdits, setNoteEdits] = useState({});
  const [deletedIds, setDeletedIds] = useState([]);

  // A gone run removed from the inspector disappears without a refetch. It is
  // taken out of the TREE and the lane is laid out again — NOT filtered out of
  // the finished graph, which would leave its edges hanging in mid-air pointing
  // at a card that is no longer there. removeRunFromTree is the same helper the
  // in-card graph uses, so children re-root the same way in both.
  const shown = useMemo(() => (entries || []).map((e) => {
    if (!e.tree) return { ...e, graph: null };
    const tree = deletedIds.reduce((t, id) => removeRunFromTree(t, id), e.tree);
    return { ...e, graph: buildLineageGraph(tree) };
  }), [entries, deletedIds]);

  const world = useMemo(() => stackLanes(shown.map((e) => ({
    ...e, width: e.graph?.width || 0, height: e.graph?.height || 0,
  }))), [shown]);

  // Measure the frame. The board is fitted to it, so an unmeasured frame would
  // mean an invisible board on first paint.
  useEffect(() => {
    const el = frameRef.current;
    if (!el) return undefined;
    const measure = () => setViewport({ width: el.clientWidth, height: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Auto-fit until the user takes over. `touched` is what makes the canvas feel
  // like a board and not a slideshow: once you have zoomed or panned, a lane
  // finishing its load must NOT yank your view back to a fit.
  const touched = useRef(false);
  const fitSignature = `${world.width}x${world.height}:${viewport.width}x${viewport.height}`;
  const lastFit = useRef('');
  useEffect(() => {
    if (touched.current || lastFit.current === fitSignature) return;
    if (!viewport.width || !viewport.height) return;
    lastFit.current = fitSignature;
    setView(initialView(world, viewport));
  }, [fitSignature, world, viewport]);

  const applyView = useCallback((next) => {
    touched.current = true;
    setView(clampView(next, world, viewport));
  }, [world, viewport]);

  const fitNow = useCallback(() => {
    touched.current = false;
    lastFit.current = '';
    if (viewport.width && viewport.height) setView(fitView(world, viewport));
  }, [world, viewport]);

  const zoomByButton = useCallback((factor) => {
    const anchor = { x: viewport.width / 2, y: viewport.height / 2 };
    applyView(zoomAt(view, factor, anchor));
  }, [applyView, view, viewport]);

  // The wheel listener is bound once per applyView identity; it reads the live
  // view through a ref so it never zooms from a stale one.
  const viewRef = useRef(view);
  useEffect(() => { viewRef.current = view; }, [view]);

  // Wheel zoom needs a NON-PASSIVE listener: React's onWheel is registered
  // passive, so preventDefault() there is ignored and the page scrolls behind
  // the board. Hence the manual native listener.
  useEffect(() => {
    const el = frameRef.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const anchor = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      // A trackpad pinch arrives as ctrl+wheel with small deltas; a mouse wheel
      // as large ones. Normalising on the sign keeps both feeling the same.
      const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      applyView(zoomAt(viewRef.current, factor, anchor));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [applyView]);

  // --- pointer gestures (pan with one, pinch with two) -----------------------
  const pointers = useRef(new Map());
  const pan = useRef(null);
  const pinch = useRef(null);

  const localPoint = (e) => {
    const rect = frameRef.current?.getBoundingClientRect();
    return { x: e.clientX - (rect?.left || 0), y: e.clientY - (rect?.top || 0) };
  };

  const onPointerDown = useCallback((e) => {
    // A press on a card or a pill is an inspection, never a pan.
    if (e.target.closest?.('.lds-gcard') || e.target.closest?.('.lds-ckpill-wrap')) return;
    pointers.current.set(e.pointerId, localPoint(e));
    frameRef.current?.setPointerCapture?.(e.pointerId);
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      pinch.current = { dist: pinchDistance(a, b), scale: viewRef.current.scale };
      pan.current = null;
    } else if (pointers.current.size === 1) {
      pan.current = { ...localPoint(e), tx: viewRef.current.tx, ty: viewRef.current.ty };
    }
    frameRef.current?.classList.add('is-grabbing');
  }, []);

  const onPointerMove = useCallback((e) => {
    if (!pointers.current.has(e.pointerId)) return;
    pointers.current.set(e.pointerId, localPoint(e));
    if (pointers.current.size >= 2 && pinch.current) {
      const [a, b] = [...pointers.current.values()];
      const dist = pinchDistance(a, b);
      if (!pinch.current.dist) return;
      const target = clampScale(pinch.current.scale * (dist / pinch.current.dist));
      applyView(zoomAt(viewRef.current, target / clampScale(viewRef.current.scale),
        pinchCenter(a, b)));
      return;
    }
    if (!pan.current) return;
    const p = localPoint(e);
    applyView(panBy({ ...viewRef.current, tx: pan.current.tx, ty: pan.current.ty },
      p.x - pan.current.x, p.y - pan.current.y));
  }, [applyView]);

  const endPointer = useCallback((e) => {
    pointers.current.delete(e.pointerId);
    frameRef.current?.releasePointerCapture?.(e.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
    if (pointers.current.size === 0) {
      pan.current = null;
      frameRef.current?.classList.remove('is-grabbing');
    }
  }, []);

  // --- inspection / compare (identical rules to the in-card graph) -----------
  const nodeById = useMemo(() => {
    const m = new Map();
    for (const e of shown) for (const n of (e.graph?.nodes || [])) m.set(n.node.record_id, n.node);
    return m;
  }, [shown]);

  const ancestors = useMemo(() => {
    const m = new Map();
    for (const e of shown) {
      for (const [id, set] of (e.graph?.ancestorsOf || new Map())) m.set(id, set);
    }
    return m;
  }, [shown]);

  const litNodes = useMemo(() => {
    const s = new Set();
    if (hoverId != null) {
      s.add(hoverId);
      for (const a of (ancestors.get(hoverId) || [])) s.add(a);
    }
    return s;
  }, [hoverId, ancestors]);
  const isLit = useCallback((id) => litNodes.has(id), [litNodes]);

  const onHover = useCallback((id, leaving) => {
    if (id == null) setHoverId((cur) => (cur === leaving ? null : cur));
    else setHoverId(id);
  }, []);

  const onNodeClick = useCallback((node, e) => {
    if (e && e.shiftKey) {
      setSelectedForDiff((sel) => toggleDiffSelection(sel, node.record_id));
      return;
    }
    setOpenNode(node);
  }, []);

  const diffRole = useCallback((id) => {
    const i = selectedForDiff.indexOf(id);
    return i === 0 ? 'A' : i === 1 ? 'B' : null;
  }, [selectedForDiff]);

  const noteOf = useCallback((node) => noteEdits[node.record_id] || node, [noteEdits]);
  const handleNodeChanged = useCallback((updated) => {
    setNoteEdits((m) => ({ ...m, [updated.record_id]: updated }));
    setOpenNode((cur) => (cur && cur.record_id === updated.record_id ? updated : cur));
  }, []);
  const handleNodeDeleted = useCallback((recordId) => {
    setDeletedIds((ids) => (ids.includes(recordId) ? ids : [...ids, recordId]));
    setOpenNode(null);
  }, []);

  const pct = Math.round(clampScale(view.scale) * 100);
  const empty = !world.lanes.length;

  return (
    <>
      {/* The edge gradients + glow, defined ONCE for the whole page: every lane's
          <svg> references them by id (see lineageEdges.jsx). */}
      <svg width="0" height="0" aria-hidden className="absolute"><LineageEdgeDefs /></svg>

      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => zoomByButton(1 / ZOOM_STEP)}
            disabled={view.scale <= MIN_SCALE + 1e-9}
            title="Zoom out" aria-label="Zoom out"
            className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-app/60 text-content-muted hover:text-content disabled:opacity-40">−</button>
          <span className="min-w-[3.25rem] text-center text-content-muted text-[0.6875rem] tabular-nums">{pct}%</span>
          <button type="button" onClick={() => zoomByButton(ZOOM_STEP)}
            disabled={view.scale >= MAX_SCALE - 1e-9}
            title="Zoom in" aria-label="Zoom in"
            className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-app/60 text-content-muted hover:text-content disabled:opacity-40">+</button>
        </div>
        <button type="button" onClick={fitNow}
          title="Fit the whole board in view"
          className="flex h-9 items-center rounded-md border border-border bg-app/60 px-3 text-content-muted text-[0.6875rem] font-semibold hover:text-content">
          Fit
        </button>
        <span className="ml-auto hidden text-content-subtle text-[0.625rem] sm:inline">
          Drag to pan · wheel to zoom · click a run to inspect · <span className="font-semibold">⇧ Shift-click</span> two runs to compare
        </span>
        {selectedForDiff.length > 0 && (
          <button type="button" onClick={() => setSelectedForDiff([])}
            className="rounded-md border border-amber-400/50 bg-amber-500/10 px-2 py-1 text-amber-100 text-[0.625rem]">
            Clear compare ({selectedForDiff.length})
          </button>
        )}
      </div>

      <div
        ref={frameRef}
        data-testid="lora-canvas-frame"
        // select-none: shift-click is the compare gesture, and shift-click is ALSO
        // the browser's extend-selection — without this, comparing two runs paints
        // half the board blue.
        className="lds-canvas-frame relative h-[65vh] min-h-[320px] w-full select-none touch-none overflow-hidden rounded-xl border border-border bg-app/40"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}>
        {empty ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-content-subtle text-[0.8125rem]">
            No dataset selected — pick one in the filter above to put its runs on the board.
          </div>
        ) : (
          <div style={{ position: 'absolute', left: 0, top: 0,
            width: Math.max(world.width, 1), height: Math.max(world.height, 1),
            transform: viewTransform(view), transformOrigin: '0 0' }}>
            {world.lanes.map((lane) => (
              <div key={lane.datasetId}>
                <LaneHeader lane={lane} />
                <LaneGraph lane={lane} isLit={isLit} onHover={onHover}
                  onNodeClick={onNodeClick} diffRole={diffRole} noteOf={noteOf} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* One drawer at a time: two picked runs → the compare diff, otherwise the
          single-run inspector. Both are the EXISTING panels, hosted unchanged —
          and because the board holds several datasets, the compare now works
          across them for free. */}
      {selectedForDiff.length === 2 ? (
        <LineageDiffPanel
          a={nodeById.get(selectedForDiff[0])}
          b={nodeById.get(selectedForDiff[1])}
          onClose={() => setSelectedForDiff([])} />
      ) : (
        <LineageDetailPanel node={openNode} onClose={() => setOpenNode(null)}
          onNodeChanged={handleNodeChanged} onNodeDeleted={handleNodeDeleted} />
      )}
    </>
  );
}
