import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildLineageGraph, CARD_W } from '../../utils/lineageGraph';
import {
  LANE_HEADER_H, MAX_SCALE, MIN_SCALE,
  clampScale, clampView, fitView, initialView, panBy, pinchCenter, pinchDistance,
  stackLanes, viewTransform, zoomAt,
} from '../../utils/canvasLayout';
import { applyPlacement, pinSnapshot, toOverrideMap } from '../../utils/canvasPlacement';
import { GraphCard, CheckpointPill } from '../dataset/lineageNodes';
import { LineageEdgeDefs, LineageEdges } from '../dataset/lineageEdges';
import { noteBadge, toggleDiffSelection } from '../dataset/lineageDetail.js';
import { removeRunFromTree } from '../../utils/runDeletable.js';
import LineageDetailPanel from '../dataset/LineageDetailPanel';
import LineageDiffPanel from '../dataset/LineageDiffPanel';
import { HelpBadge } from '../../help/HelpMode';

/* ◉ The LoRA Canvas surface — every selected dataset's genealogy on ONE board,
   with zoom and pan.

   It draws with the SAME card, pill and edge components as the graph embedded in
   a run's card (components/dataset/lineageNodes + lineageEdges); the geometry of
   each dataset's tree is still utils/lineageGraph.js. What is new here is only
   the surface: several trees stacked into lanes, and a viewport you can move.

   Slice 2 adds direct manipulation: cards can be dragged, and where they land is
   remembered (utils/canvasPlacement.js + the canvas_node_position table).
   Nothing generates from here yet (slice 3), so a checkpoint pill opens its
   run's inspector rather than pretending to offer actions it cannot perform — a
   dead click would be worse than no click. The in-card graph keeps every one of
   those actions until the canvas actually reaches parity.

   Gestures: wheel (or trackpad pinch, which arrives as ctrl+wheel) zooms around
   the pointer; dragging the background pans; two fingers pinch-zoom; dragging a
   card moves it.

   ⚠️ Moving a card and moving the view are the SAME physical gesture. With a
   mouse, hit-testing settles it: the press either landed on a card or it did
   not. On touch there is nothing to hit-test with — a finger on a card could
   mean either — so the finger PANS by default and only starts moving the card
   after a long press, which is the gesture every touch UI already uses for
   "pick this up". Moving before the press completes cancels it, so a flick that
   happens to start on a card still scrolls the board. */

const ZOOM_STEP = 1.25;
// How long a finger must rest on a card before it picks it up. Long enough not
// to fire on a flick that starts on a card, short enough not to feel broken.
const LONG_PRESS_MS = 420;
// Screen pixels of travel before a press counts as a drag. Below it the gesture
// is still a click, so inspecting a run never depends on holding perfectly
// still — and a 2-px twitch must not write a position to the database.
const DRAG_SLOP = 4;

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
function LaneGraph({ lane, isLit, onHover, onNodeClick, diffRole, noteOf, liftedId }) {
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
            {/* data-canvas-node is the hit-test handle: the pointer handlers on
                the frame read the lane + run off it to know WHAT was grabbed,
                without every card needing its own listener. */}
            <div data-canvas-node="" data-dataset-id={lane.datasetId} data-record-id={n.node.record_id}
              style={{ position: 'relative', width: CARD_W, height: n.cellH,
                ...(liftedId === n.node.record_id
                  ? { filter: 'drop-shadow(0 6px 14px rgba(0,0,0,0.55))', opacity: 0.92 }
                  : null) }}
              className={liftedId === n.node.record_id ? 'lds-gnode-lifted' : undefined}>
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

export default function LineageCanvas({ entries, positions, onPinLane, onTidyUp }) {
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

  // --- placement: the automatic tree ⊕ what the user moved ------------------
  // A drag is applied as a temporary override on top of the stored map, over a
  // BASELINE captured when the drag started. The baseline matters: dropping a
  // single override onto an otherwise-automatic lane would make that lane
  // "arranged" halfway through the gesture, and applyPlacement would treat every
  // other card as a new arrival to slide out of the way. Freezing the lane at
  // the moment the finger lands keeps the rest of the board perfectly still.
  const [drag, setDrag] = useState(null);   // {datasetId, recordId, x, y, baseline}

  const placed = useMemo(() => shown.map((e) => {
    if (!e.graph) return e;
    let ov = positions?.[e.datasetId] || {};
    if (drag && drag.datasetId === e.datasetId) {
      ov = { ...drag.baseline, [drag.recordId]: { x: drag.x, y: drag.y } };
    }
    return { ...e, graph: applyPlacement(e.graph, ov) };
  }), [shown, positions, drag]);

  // A lane that gained a run since it was arranged reports the new card's spot;
  // persisting it is what makes "a new run moves nothing" survive the NEXT
  // reload too. Guarded by a seen-set so a failed write cannot become a loop.
  const pinned = useRef(new Set());
  useEffect(() => {
    for (const lane of placed) {
      const pins = lane.graph?.pendingPins;
      if (!pins?.length) continue;
      const key = `${lane.datasetId}:${pins.map((p) => p.record_id).join(',')}`;
      if (pinned.current.has(key)) continue;
      pinned.current.add(key);
      onPinLane?.(lane.datasetId, pins);
    }
  }, [placed, onPinLane]);

  const world = useMemo(() => stackLanes(placed.map((e) => ({
    ...e, width: e.graph?.width || 0, height: e.graph?.height || 0,
  }))), [placed]);

  // The latest placement, for the pointer handlers (which must not re-bind on
  // every board change just to read a card's current position).
  const placedRef = useRef(placed);
  useEffect(() => { placedRef.current = placed; }, [placed]);

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

  // --- node dragging ---------------------------------------------------------
  const dragRef = useRef(null);      // {datasetId, recordId, sx, sy, ox, oy, moved}
  const longPress = useRef(null);    // touch: the pending pick-up
  const suppressClick = useRef(false);

  const cancelLongPress = () => {
    if (longPress.current) { clearTimeout(longPress.current); longPress.current = null; }
  };

  /** Pick a card up: freeze its lane as it looks RIGHT NOW, then follow the
   *  pointer. `origin` is the screen point the gesture started from. */
  const beginDrag = useCallback((datasetId, recordId, origin) => {
    const lane = placedRef.current.find((l) => l.datasetId === datasetId);
    const n = lane?.graph?.nodes.find((x) => x.node.record_id === recordId);
    if (!n) return;
    dragRef.current = { datasetId, recordId, sx: origin.x, sy: origin.y,
      ox: n.x, oy: n.y, x: n.x, y: n.y, moved: false };
    setDrag({ datasetId, recordId, x: n.x, y: n.y,
      baseline: toOverrideMap(pinSnapshot(lane.graph, recordId, n.x, n.y)) });
    pan.current = null;
  }, []);

  const onPointerDown = useCallback((e) => {
    suppressClick.current = false;
    // A press on a pill is an inspection, never a drag or a pan.
    if (e.target.closest?.('.lds-ckpill-wrap')) return;
    const card = e.target.closest?.('[data-canvas-node]');
    const at = localPoint(e);
    if (card && e.pointerType !== 'touch') {
      // Mouse / pen: the press landed on a card, so it IS the card that moves.
      frameRef.current?.setPointerCapture?.(e.pointerId);
      beginDrag(Number(card.dataset.datasetId), Number(card.dataset.recordId), at);
      return;
    }
    pointers.current.set(e.pointerId, at);
    frameRef.current?.setPointerCapture?.(e.pointerId);
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      pinch.current = { dist: pinchDistance(a, b), scale: viewRef.current.scale };
      pan.current = null;
      cancelLongPress();
    } else if (pointers.current.size === 1) {
      pan.current = { ...at, tx: viewRef.current.tx, ty: viewRef.current.ty };
      if (card) {
        // Touch on a card: pan for now, pick the card up if the finger stays.
        const dsId = Number(card.dataset.datasetId);
        const recId = Number(card.dataset.recordId);
        longPress.current = setTimeout(() => {
          longPress.current = null;
          beginDrag(dsId, recId, at);
        }, LONG_PRESS_MS);
      }
    }
    frameRef.current?.classList.add('is-grabbing');
  }, [beginDrag]);

  const onPointerMove = useCallback((e) => {
    const d = dragRef.current;
    if (d) {
      const p = localPoint(e);
      const scale = clampScale(viewRef.current.scale);
      const dx = (p.x - d.sx) / scale;
      const dy = (p.y - d.sy) / scale;
      if (!d.moved && Math.hypot(p.x - d.sx, p.y - d.sy) < DRAG_SLOP) return;
      d.moved = true;
      d.x = Math.max(0, d.ox + dx);
      d.y = Math.max(0, d.oy + dy);
      setDrag((cur) => (cur ? { ...cur, x: d.x, y: d.y } : cur));
      return;
    }
    if (!pointers.current.has(e.pointerId)) return;
    const prev = pointers.current.get(e.pointerId);
    pointers.current.set(e.pointerId, localPoint(e));
    // A finger that travels is scrolling the board, not picking a card up.
    if (longPress.current && prev) {
      const p = localPoint(e);
      if (Math.hypot(p.x - prev.x, p.y - prev.y) > DRAG_SLOP) cancelLongPress();
    }
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
    cancelLongPress();
    const d = dragRef.current;
    if (d) {
      dragRef.current = null;
      // Only a gesture that actually MOVED writes anything: a plain click on a
      // card must stay a click, and must not turn its lane into an arranged one
      // behind the user's back.
      if (d.moved) {
        suppressClick.current = true;
        const lane = placedRef.current.find((l) => l.datasetId === d.datasetId);
        if (lane?.graph) onPinLane?.(d.datasetId, pinSnapshot(lane.graph, d.recordId, d.x, d.y));
      }
      setDrag(null);
    }
    pointers.current.delete(e.pointerId);
    frameRef.current?.releasePointerCapture?.(e.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
    if (pointers.current.size === 0) {
      pan.current = null;
      frameRef.current?.classList.remove('is-grabbing');
    }
  }, [onPinLane]);

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
    // A drop lands on the card it moved, so the browser fires a click right
    // after it. Swallow exactly that one — otherwise every move would also open
    // the inspector.
    if (suppressClick.current) { suppressClick.current = false; return; }
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
  // Has anything on the visible board been moved? Drives ✦ Tidy up: a button
  // that clears nothing should say so by being disabled, not by doing nothing.
  const arranged = shown.some((e) => Object.keys(positions?.[e.datasetId] || {}).length > 0);

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
        {/* The way out of an arrangement that got away from you. Twenty runs
            later a hand-tidied board can be a knot, and "move them all back by
            hand" is not an answer — this drops every remembered position and
            hands the board to the automatic tree again. */}
        <button type="button" onClick={onTidyUp} disabled={!arranged}
          title={arranged
            ? 'Forget every moved card and rebuild the automatic tree'
            : 'Nothing has been moved yet'}
          className="flex h-9 items-center gap-1 rounded-md border border-border bg-app/60 px-3 text-content-muted text-[0.6875rem] font-semibold hover:text-content disabled:opacity-40">
          <span aria-hidden>✦</span> Tidy up
        </button>
        <HelpBadge topic="canvas-arrange" />
        <span className="ml-auto hidden text-content-subtle text-[0.625rem] sm:inline">
          Drag a run to move it · drag the background to pan · wheel to zoom · click a run to inspect · <span className="font-semibold">⇧ Shift-click</span> two runs to compare
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
                  onNodeClick={onNodeClick} diffRole={diffRole} noteOf={noteOf}
                  liftedId={drag && drag.datasetId === lane.datasetId ? drag.recordId : null} />
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
