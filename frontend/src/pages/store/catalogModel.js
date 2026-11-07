// The running registry owns installed state. The catalog only adds releases
// and previews; a catalog outage must never hide an installed plugin.
export function catalogEntries(products = [], installed = []) {
  const entries = new Map(products.map(product => [product.id, {
    id: product.id, product, release: product.recommended || product.releases?.[0] || null, plugin: null,
  }]));
  for (const plugin of installed) {
    entries.set(plugin.id, { ...(entries.get(plugin.id) || { id: plugin.id, product: null, release: null }), plugin });
  }
  return [...entries.values()];
}

export function matchesFilter(entry, filter) {
  return filter === 'installed' ? Boolean(entry.plugin)
    : filter === 'updates' ? Boolean(entry.product?.update_available && entry.release) : true;
}

export function canSelectEntry({ product, release, plugin }) {
  return Boolean(release && !(release.compatibility_issues || []).length && !plugin?.pending_action
    && (!plugin || product?.update_available));
}

export function availableUpdateIds(entries) {
  return entries.filter(entry => entry.plugin && entry.product?.update_available && canSelectEntry(entry))
    .map(entry => entry.id);
}

export function catalogView(params) {
  const legacy = params.get('tab');
  const filter = params.get('filter');
  return {
    tab: legacy === 'purchases' ? 'purchases' : 'plugins',
    filter: ['all', 'installed', 'updates'].includes(filter) ? filter
      : ['installed', 'updates'].includes(legacy) ? legacy : 'all',
  };
}
