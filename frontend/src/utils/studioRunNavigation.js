/** Open the selected run's image family even after testing a different dataset or Studio lane. */
export function studioRunTarget(datasetId, family) {
  if (datasetId == null) return null;
  const query = new URLSearchParams({ lane: 'image' });
  if (family) query.set('family', family);
  return `/dataset/studio/${encodeURIComponent(datasetId)}?${query}`;
}
