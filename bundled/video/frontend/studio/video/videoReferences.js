import { PERFORMANCE_DEFAULTS, performanceSettings } from './videoPerformance.js';
import { referenceLibraryKey } from './referenceLibrary.js';

/** Reference order is the model's order: pictures, videos (with soundtrack
 * labels), then standalone audio. A soundtrack shares the Audio counter. */
export const REFERENCE_LIMITS = { image: 9, video: 3, audio: 3 };
/** The shapes the Output select offers. A clip row can also carry 'auto' (the
 *  column's default, and what an unknown value is normalised to), which is not
 *  one of them: restored as-is it leaves the control showing nothing. Every
 *  path that takes a shape from a clip filters through this. */
export const ASPECTS = ['landscape', 'portrait', 'square'];
export const REFERENCE_DEFAULTS = {
  ...PERFORMANCE_DEFAULTS,
  base: 'official', accel: 'ref8', imageSize: 'match', sparse: '',
  refmods: false,
  steps: '', frames: 124, megapixels: 0.3, seed: '', aspect: 'landscape',
};
export const REFERENCE_STORAGE = 'lds.videoReferenceDraft.v1';
export const referenceUrl = (name) => `/api/video-studio/reference${name ? `?name=${encodeURIComponent(name)}` : ''}`;

export function referencePayload(references = []) {
  return references.filter((r) => r && REFERENCE_LIMITS[r.kind] && typeof r.name === 'string' && r.name)
    .map((r) => ({ kind: r.kind, name: r.name, role: String(r.role || '').slice(0, 500),
      ...(r.kind === 'video' ? { include_audio: !!r.include_audio,
        ...(r.use_format === true ? { use_format: true } : {}) } : {}) }));
}

/** One video may supply the output format. Removing it restores the manual shape. */
export function selectReferenceFormat(references, name, checked) {
  return references.map((r) => r.kind === 'video'
    ? { ...r, use_format: r.name === name ? checked : checked ? false : r.use_format }
    : r);
}

export function referenceFormat(references = []) {
  return taggedReferences(references).find((r) => r.kind === 'video' && r.use_format === true) || null;
}

export function referenceFormatSize(reference) {
  const width = Number(reference?.source_width), height = Number(reference?.source_height);
  return Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0
    ? `${width} × ${height}` : '';
}

export function taggedReferences(references = []) {
  let audio = 0;
  return ['image', 'video', 'audio'].flatMap((kind) => references.filter((r) => r.kind === kind)
    .map((r, index) => {
      const audioTag = kind === 'video' && r.include_audio ? `<Audio ${++audio}>` : null;
      const tag = kind === 'image' ? `<Picture ${index + 1}>`
        : kind === 'video' ? `<Video ${index + 1}>` : `<Audio ${++audio}>`;
      return { ...r, tag, audioTag };
    }));
}

/** Rewrite all tags in one pass, so swapping Picture 1 and 2 cannot alias
 * both to 1. Removed references remain explicit until the author edits them. */
export function remapReferencePrompt(prompt, before, after) {
  const next = new Map();
  for (const r of taggedReferences(after)) {
    next.set(r.name, r);
    // ✂ A cut is the same reference under a new name: the tag it took over
    // follows the reference it was cut from (review, 2026-09-06 — a cut
    // turned <Video 1> into [removed Video 1] in the prompt).
    if (r.cut_from && !next.has(r.cut_from)) next.set(r.cut_from, r);
  }
  const mapping = new Map();
  for (const r of taggedReferences(before)) {
    const n = next.get(r.name);
    mapping.set(r.tag, n?.tag || `[removed ${r.tag.slice(1, -1)}]`);
    if (r.audioTag) mapping.set(r.audioTag, n?.audioTag || `[removed ${r.audioTag.slice(1, -1)}]`);
  }
  return String(prompt || '').replace(/<(?:Picture|Video|Audio) \d+>/g, (tag) => mapping.get(tag) || tag);
}

export function moveReference(references, name, direction) {
  const out = [...references];
  const at = out.findIndex((r) => r.name === name);
  if (at < 0) return out;
  const siblings = out.map((r, i) => r.kind === out[at].kind ? i : -1).filter((i) => i >= 0);
  const to = siblings[siblings.indexOf(at) + direction];
  if (to !== undefined) [out[at], out[to]] = [out[to], out[at]];
  return out;
}

export function referenceSummary(references = []) {
  return ['image', 'video', 'audio'].map((kind) => {
    const count = references.filter((r) => r.kind === kind).length;
    return count ? `${count} ${kind}${count === 1 ? '' : 's'}` : null;
  }).filter(Boolean).join(', ');
}

export function referenceDescriptors(references = []) {
  const clean = referencePayload(Array.isArray(references) ? references : []);
  return clean.map((r) => {
    const original = references.find((item) => item?.name === r.name);
    return { ...r, key: referenceLibraryKey(original), has_audio: original.has_audio,
      duration: original.duration, width: original.width, height: original.height,
      source_width: original.source_width, source_height: original.source_height,
      ...(original.cut_from ? { cut_from: original.cut_from, cut_source_duration: original.cut_source_duration } : {}),
      ...(original.library_source ? { library_source: original.library_source, source_label: original.source_label,
        frame: original.frame, start_seconds: original.start_seconds, duration_seconds: original.duration_seconds } : {}) };
  });
}

export function readReferenceDraft(storage, key = REFERENCE_STORAGE) {
  try {
    storage ??= globalThis.localStorage;
    const saved = JSON.parse(storage?.getItem(key) || 'null');
    return { active: saved?.active === true,
      references: referenceDescriptors(saved?.references),
      settings: { ...REFERENCE_DEFAULTS, ...(saved?.settings || {}), ...performanceSettings(saved?.settings),
        base: ['official', 'light', 'eros', 'fused'].includes(saved?.settings?.base) ? saved.settings.base : 'official',
        accel: ['', 'ref4', 'ref8', 'vdn'].includes(saved?.settings?.accel) ? saved.settings.accel : REFERENCE_DEFAULTS.accel,
        imageSize: saved?.settings?.imageSize === 'max' ? 'max' : 'match',
        aspect: ASPECTS.includes(saved?.settings?.aspect)
          ? saved.settings.aspect : REFERENCE_DEFAULTS.aspect },
      firstFrame: saved?.firstFrame?.image ? saved.firstFrame : null,
      endFrame: saved?.endFrame?.image ? saved.endFrame : null };
  } catch { return { active: false, references: [], settings: { ...REFERENCE_DEFAULTS }, firstFrame: null, endFrame: null }; }
}

export function writeReferenceDraft(draft, storage, key = REFERENCE_STORAGE) {
  try {
    storage ??= globalThis.localStorage;
    storage?.setItem(key, JSON.stringify({ ...draft, references: referenceDescriptors(draft.references) }));
  }
  catch { /* Storage disabled: the current take still works. */ }
}


// ✂ Cut a staged reference video to an interval (2026-09-06): the same bounds
// as a library excerpt (2–15 s, inside the copy), never the whole video.
export const CUT_MIN_SECONDS = 2;
export const CUT_MAX_SECONDS = 15;
export function cutInterval(reference, start, duration) {
  const total = Number(reference?.duration);
  const s = Number(start);
  const d = Number(duration);
  if (!Number.isFinite(total) || total <= 0) return { error: 'The video duration could not be read.' };
  if (String(start).trim() === '' || !Number.isFinite(s) || s < 0) return { error: 'Enter a start time of 0 seconds or later.' };
  if (String(duration).trim() === '' || !Number.isFinite(d) || d < CUT_MIN_SECONDS || d > CUT_MAX_SECONDS) return { error: `Choose ${CUT_MIN_SECONDS}–${CUT_MAX_SECONDS} seconds.` };
  if (s + d > total + 0.001) return { error: 'The interval extends past the end of this video.' };
  if (s <= 0.0005 && d >= total - 0.0005) return { error: 'Choose a shorter interval than the whole video.' };
  return { start: s, duration: d, error: '' };
}
export function cutDefaultDuration(total) {
  // A valid interval as the block opens: 5 s (the figure the feature cites) or,
  // on a short copy, half a second less than the whole — never the whole.
  const t = Number(total) || 0;
  if (t > 5.05) return 5;
  return Math.max(CUT_MIN_SECONDS, Math.floor((t - 0.5) * 10) / 10);
}
export function cutBody(reference, start, duration) {
  return { kind: 'video', cut_from: reference.name, start_seconds: Number(start), duration_seconds: Number(duration),
    role: reference.role || '', include_audio: !!reference.include_audio && reference.has_audio !== false };
}
export function replaceReference(references, name, replacement) {
  return references.map((r) => (r.name === name
    ? { ...replacement, role: r.role || replacement.role || '', use_format: r.use_format === true, key: r.key || replacement.key || replacement.name }
    : r));
}
