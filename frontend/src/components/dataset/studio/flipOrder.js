// react-frontend/src/components/dataset/studio/flipOrder.js
/**
 * Results lightbox navigation fulfills the request to compare strengths of the SAME rendering with
 * identical seed without closing the viewer. Strength variants must be ADJACENT. keyOf(cell)
 * returns a sort tuple with STRENGTH LAST: group by all other rendering attributes, then ascending
 * strength. Neighboring images therefore differ only in strength. Keep only displayable cells with
 * generated, existing files that the lightbox can open.
 */
function cmpTuple(a, b) {
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    const x = a[i];
    const y = b[i];
    if (x === y) continue;
    if (typeof x === 'number' && typeof y === 'number') return x - y;
    return String(x ?? '').localeCompare(String(y ?? ''), undefined, { numeric: true });
  }
  return 0;
}

export function flipOrder(cells, keyOf) {
  return (cells || [])
    .filter((c) => c.status === 'done' && c.filename)
    .map((c) => ({ c, k: keyOf(c) }))
    .sort((a, b) => cmpTuple(a.k, b.k))
    .map((x) => x.c);
}
