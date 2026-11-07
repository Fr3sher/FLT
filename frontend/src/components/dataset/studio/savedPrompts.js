/*
 * Pure prompt-history normalization and search rules, like promptBatch.js. Pure modules are
 * directly testable, and Dataset Studio and Canvas Generate from the board share one rule instead
 * of duplicating it.
 */

/**
 * Normalize either API history-entry shape. Before Flask restart, /api/studio/recent-prompts may
 * return STRINGS; afterward it returns {prompt, thumbnail, thumb_dataset_id, thumb_rating, count}.
 * Route all readers through here so backward compatibility is handled once.
 */
export function normalizeSavedPrompt(item) {
  const raw = typeof item === 'string' ? { prompt: item } : (item || {});
  return {
    prompt: raw.prompt || '',
    thumbnail: raw.thumbnail || null,
    thumbDatasetId: raw.thumb_dataset_id ?? null,
    liked: raw.thumb_rating === 1,
    count: Number(raw.count) || 0,
  };
}

/**
 * History search requires ALL query words. Test prompts are long, around 500 characters median,
 * and often share their beginning. Searching bathroom mirror should find entries even when the
 * words are 200 characters apart, unlike raw-substring matching. Empty query returns the full list
 * in newest-first order.
 */
export function filterSavedPrompts(items, query) {
  const list = Array.isArray(items) ? items : [];
  const words = String(query || '').toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return list;
  return list.filter((item) => {
    const text = normalizeSavedPrompt(item).prompt.toLowerCase();
    return words.every((w) => text.includes(w));
  });
}
