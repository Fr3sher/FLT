// Presentation of persisted file identifiers survives the generating plugin.
export function checkpointFileLabel(value) {
  if (value === null || value === undefined || value === '') return ''
  const tail = String(value).split(/[\\/]/).pop() || ''
  return tail.replace(/\.(safetensors|ckpt|pt|sft)$/i, '')
}

export function runRowDomId(source, id) {
  if (id == null) return null;
  return `run-${source === 'cloud' ? 'cloud' : 'local'}-${id}`;
}

export const baseName = (p) => String(p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || String(p || '');

export const fmtBytes = (b) => {
  if (b == null) return '';
  if (b >= 1e9) return `${(b / 1e9).toFixed(1)} GB`;
  if (b >= 1e6) return `${Math.round(b / 1e6)} MB`;
  return `${Math.max(1, Math.round(b / 1e3))} KB`;
};

export function defaultValueAt(configDefaults, section, field) {
  const s = (configDefaults || {})[section];
  if (!s || typeof s !== 'object') return undefined;
  return Object.prototype.hasOwnProperty.call(s, field) ? s[field] : undefined;
}

export function formatSize(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  const v = Number(n);
  if (v <= 0) return 'empty';
  if (v < 1e6) return `${Math.max(1, Math.round(v / 1e3))} KB`;
  if (v < 1e9) return `${Math.round(v / 1e6)} MB`;
  return `${(v / 1e9).toFixed(1)} GB`;
}

export function deleteDestination(mode) {
  if (mode === 'trash') return 'your system Recycle Bin';
  if (mode === 'app_trash') return "the app's Trash (Settings ▸ Storage)";
  return 'nowhere — they are deleted for good';
}

export function isRecoverable(mode) {
  return mode === 'trash' || mode === 'app_trash';
}

const PROSE_STOP_WORDS = new Set([
  'the', 'and', 'with', 'that', 'this', 'from', 'into', 'onto', 'over', 'under',
  'their', 'there', 'while', 'where', 'which', 'who', 'whose', 'are', 'was',
  'were', 'has', 'have', 'had', 'for', 'but', 'not', 'its', 'his', 'her',
  'him', 'she', 'they', 'them', 'you', 'your', 'our', 'out', 'off', 'near',
  'through', 'between', 'beside', 'behind', 'front', 'image', 'scene', 'shows',
  'showing', 'captures', 'featuring', 'wearing', 'against', 'within', 'being',
  'person', 'woman', 'women', 'man', 'men', 'someone', 'something', 'each',
  'some', 'very', 'more', 'most', 'also', 'about', 'above', 'below',
])

function proseTerms(caption) {
  const words = String(caption || '').toLowerCase().match(/[\p{L}\p{N}][\p{L}\p{N}'’-]{2,}/gu) || []
  return words.filter((word) => !PROSE_STOP_WORDS.has(word))
}

export function captionFrequencyEntries(captions, mode = 'prose', limit = 30) {
  const counts = new Map()
  for (const caption of captions || []) {
    const rawTerms = mode === 'booru'
      ? String(caption || '').split(',').map((tag) => tag.trim().toLowerCase()).filter(Boolean)
      : proseTerms(caption)
    // The count means “in N captions”, not raw repetitions inside one caption.
    for (const term of new Set(rawTerms)) counts.set(term, (counts.get(term) || 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
}
