export const CANVAS_FAMILY_SELECTION_KEY = 'lds.canvasModelFamilies';

export const CANVAS_FAMILY_LABELS = {
  zimage: 'Z-Image', krea: 'Krea 2', sdxl: 'SDXL',
  flux: 'FLUX.1', flux2klein: 'FLUX.2 Klein', anima: 'Anima',
};

const FAMILY_ORDER = Object.keys(CANVAS_FAMILY_LABELS);
const asFamilies = (value) => (Array.isArray(value) ? value : [])
  .filter((family) => typeof family === 'string')
  .map((family) => family.trim())
  .filter(Boolean)
  .filter((family, index, all) => all.indexOf(family) === index);

export const familyLabel = (family) => CANVAS_FAMILY_LABELS[family] || family;

export function availableModelFamilies(datasets) {
  const found = asFamilies((datasets || []).flatMap((d) => d?.families || []));
  return found.sort((a, b) => {
    const ai = FAMILY_ORDER.indexOf(a);
    const bi = FAMILY_ORDER.indexOf(b);
    if (ai < 0 && bi < 0) return a.localeCompare(b);
    if (ai < 0) return 1;
    if (bi < 0) return -1;
    return ai - bi;
  });
}

export function readFamilySelection(store, key = CANVAS_FAMILY_SELECTION_KEY) {
  try {
    const raw = store?.getItem(key);
    if (raw == null) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? asFamilies(parsed) : null;
  } catch {
    return null;
  }
}

export function writeFamilySelection(store, families, key = CANVAS_FAMILY_SELECTION_KEY) {
  try {
    store?.setItem(key, JSON.stringify(asFamilies(families)));
    return true;
  } catch {
    return false;
  }
}

export function resolveFamilySelection(available, stored) {
  const all = asFamilies(available);
  if (stored == null) return all;
  const wanted = new Set(asFamilies(stored));
  return all.filter((family) => wanted.has(family));
}

export function toggleFamilySelection(selected, family, available) {
  const all = asFamilies(available);
  const current = new Set(asFamilies(selected));
  if (current.has(family)) current.delete(family); else current.add(family);
  return all.filter((item) => current.has(item));
}

export function filterDatasetIdsByFamilies(datasets, selectedIds, selectedFamilies) {
  const wantedIds = new Set((selectedIds || []).map(Number));
  const wantedFamilies = new Set(asFamilies(selectedFamilies));
  return (datasets || [])
    .filter((d) => wantedIds.has(Number(d?.id))
      && asFamilies(d?.families).some((family) => wantedFamilies.has(family)))
    .map((d) => Number(d.id));
}

/** Remove runs from unselected model families while keeping the lineage shape
 * valid: edges to hidden runs disappear and a retained orphan becomes a root. */
export function filterLineageTreeByFamilies(tree, selectedFamilies) {
  if (!tree || !Array.isArray(tree.nodes)) return tree;
  const wanted = new Set(asFamilies(selectedFamilies));
  const nodes = tree.nodes.filter((node) => wanted.has(node?.train_type));
  const ids = new Set(nodes.map((node) => node.record_id));
  const fallbackCurrent = nodes[nodes.length - 1]?.record_id ?? null;
  return {
    ...tree,
    nodes,
    edges: (Array.isArray(tree.edges) ? tree.edges : [])
      .filter((edge) => ids.has(edge?.parent) && ids.has(edge?.child)),
    root_id: ids.has(tree.root_id) ? tree.root_id : (nodes[0]?.record_id ?? null),
    current_id: ids.has(tree.current_id) ? tree.current_id : fallbackCurrent,
  };
}
