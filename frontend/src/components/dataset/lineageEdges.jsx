/* ◉ The edges of a lineage — the flowing bezier connectors that read parent→child.

   Extracted from RunLineageGraph.jsx so the LoRA Canvas draws the SAME edges as
   the in-card graph rather than a lookalike: same gradients, same trunk
   brightening, same dashed-and-dimmed superseded branch, same draw-in delay.

   ⚠️ SVG gradient/filter ids are DOCUMENT-global. `LineageEdgeDefs` must be
   rendered exactly ONCE per page: the in-card graph puts it inside its own
   <svg>, while the canvas — which draws one <svg> per dataset lane — renders it
   once at page level and every lane references the same four ids. Rendering it
   per lane would be N copies of the same id in one document; `url(#…)` would
   still resolve (to the first), but it would be a lie waiting to become a bug
   the day the definitions differ. */

/** The gradients + glow filter every lineage edge paints with. Render once per
 *  document (see the warning above). */
export function LineageEdgeDefs() {
  return (
    <defs>
      {/* edges flow left→right = parent→child, so a horizontal gradient in
          the path's own box paints the direction of descent. */}
      <linearGradient id="lds-edge-normal" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="rgb(148 163 184)" stopOpacity="0.15" />
        <stop offset="1" stopColor="rgb(203 213 225)" stopOpacity="0.4" />
      </linearGradient>
      <linearGradient id="lds-edge-spine" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#6366f1" stopOpacity="0.6" />
        <stop offset="1" stopColor="#a5b4fc" stopOpacity="0.98" />
      </linearGradient>
      <linearGradient id="lds-edge-super" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#f59e0b" stopOpacity="0.12" />
        <stop offset="1" stopColor="#fbbf24" stopOpacity="0.5" />
      </linearGradient>
      <filter id="lds-edge-glow" x="-20%" y="-40%" width="140%" height="180%">
        <feGaussianBlur stdDeviation="2.2" result="b" />
        <feMerge>
          <feMergeNode in="b" /><feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
  );
}

/** Every edge of one graph: the glow halo underneath the trunk, then the crisp
 *  cores on top. `isLit(id)` says whether a node is on the hovered path — an
 *  edge whose two ends are both lit is drawn like the trunk, so hovering a run
 *  traces its whole descent back to the root. Pass `() => false` for a surface
 *  with no hover story. */
export function LineageEdges({ edges, isLit }) {
  const lit = typeof isLit === 'function' ? isLit : () => false;
  return (
    <>
      {/* Glow halo underneath the trunk (root→current), so even short hops read
          as a lit ribbon. Drawn first, then the crisp cores on top. */}
      <g fill="none" strokeLinecap="round" aria-hidden>
        {edges.map((e) => {
          if (!(e.onSpine || (lit(e.parentId) && lit(e.childId))) || e.superseded) return null;
          return (
            <path key={`glow-${e.parentId}-${e.childId}`}
              d={e.d} stroke="url(#lds-edge-spine)" strokeWidth="5"
              opacity="0.5" filter="url(#lds-edge-glow)" />
          );
        })}
      </g>
      <g fill="none" strokeLinecap="round">
        {edges.map((e, i) => {
          const both = lit(e.parentId) && lit(e.childId);
          const spine = e.onSpine || both;
          const grad = e.superseded ? 'lds-edge-super' : spine ? 'lds-edge-spine' : 'lds-edge-normal';
          return (
            <path key={`${e.parentId}-${e.childId}`}
              className="lds-ledge"
              d={e.d}
              stroke={`url(#${grad})`}
              strokeWidth={spine ? 2.6 : 1.5}
              strokeDasharray={e.superseded ? '2 4' : undefined}
              pathLength="1"
              style={{ '--draw-delay': `${Math.min(i, 10) * 60 + 120}ms` }} />
          );
        })}
      </g>
    </>
  );
}
