/* The collapsible GROUPS a long settings section is organised into, and the
 * little state around them. PURE JS — `node --test` covers every decision.
 *
 * WHY GROUPS AND NOT SUB-PAGES. The Image engines section had grown into a
 * single wall of eleven cards — API keys next to Klein pins next to LoRA
 * presets next to the improve prompt — and "where is the thing I came for"
 * was answered by scrolling (reported from a tablet, mid preset editing).
 * Groups keep every deep-link alive for free: each group is a NATIVE
 * <details>, and help/revealTarget.openCollapsedAncestors already opens a
 * collapsed <details> on the way to a ?focus= field — so Settings search and
 * every "Open in Settings →" link land INSIDE the right group with zero new
 * wiring. Sub-pages would have needed an alias for every existing link.
 *
 * The <details> stay UNCONTROLLED on purpose: the reveal helper flips
 * `open` on the DOM node directly, and a React-controlled `open` prop would
 * fight it on the next render. The initial state is read once at mount; the
 * prop value then never changes, so React never writes over a user's toggle.
 */

/** The Image engines groups, in display order. `id` is stored in localStorage
 *  and used in DOM anchors — never rename one without an alias. */
import { BarChart3, Bot, Box, Cloud, Drama, Dumbbell, Eraser, ImageDown, KeyRound, Map, Package, PenLine, Puzzle, SlidersHorizontal, SlidersVertical, Trash2 } from 'lucide-react';
import { contributions } from '../../plugins/registry.js';
export const ENGINES_GROUPS = [
  // The id stays 'engines-keys' (persisted as this group's open state and in
  // the deep links); the label follows the fact that the API keys moved to
  // their engines' plugin, whose own settings page hosts its groups.
  { id: 'engines-keys', title: 'Engines', icon: KeyRound,
    blurb: 'Which engines are on, and which one opens preselected.' },
  { id: 'klein', title: 'Klein (local)', icon: SlidersHorizontal,
    blurb: 'Model file pins and generation quality for the local Klein engine.' },
  // The id stays 'krea' — it is persisted in localStorage as this group's
  // open/closed state and used by the settings deep links. Only the label
  // follows the fact that the group now holds TWO different Krea graphs: the
  // Edit engine, and the hi-res fix that belongs to the generation one.
  { id: 'krea', title: 'Krea 2 (local)', icon: SlidersVertical,
    blurb: 'The Edit engine — base model, identity LoRA and its dials — and the generation hi-res fix.' },
  { id: 'lora-presets', title: 'Generation LoRA presets', icon: Puzzle,
    blurb: 'Named LoRA chains you pick per run — one list per local engine.' },
  // Id unchanged (localStorage + deep links); the label follows the card that
  // joined it — the finishing pass belongs to the improve OUTPUT, not to either
  // engine, so it has nowhere better to live.
  { id: 'prompts', title: 'Identity prompts (advanced)', icon: PenLine,
    blurb: 'Identity prompts and local generation instructions per subject type.' },
]

/** Local tools and their shared processing/network budgets. */
export const LOCAL_TOOLS_GROUPS = [
  { id: 'comfyui', title: 'ComfyUI', icon: Puzzle,
    blurb: 'The local generation backend — API URL, install folder, model paths.' },
  // The id stays 'ollama' on purpose — it is persisted in localStorage as the
  // group's open/closed state and used by the settings deep links. Only the
  // label follows the fact that there are now two providers behind it.
  { id: 'ollama', title: 'Local LLM', icon: Bot,
    blurb: 'Ollama or LM Studio — captions, descriptions, framing, prompt help.' },
  { id: 'aitoolkit', title: 'ai-toolkit', icon: Dumbbell,
    blurb: 'The local trainer — install folder and its Python.' },
  { id: 'timeouts', title: 'Time limits', icon: SlidersHorizontal,
    blurb: 'Repair, processing and network waits for slow or busy hardware.' },
]

/** ✍️ Captioning & quality. */
export const CAPTIONING_GROUPS = [
  { id: 'import', title: 'Import & image size', icon: ImageDown,
    blurb: 'What happens to a photo as it enters — stored format, resolution budgets.' },
  { id: 'captioning', title: 'Captioning', icon: PenLine,
    blurb: 'Which captioner writes the training captions, and how.' },
  { id: 'watermarks', title: 'Watermark inpainting', icon: Eraser,
    blurb: 'The clean-watermarks pass — engine and behaviour.' },
  { id: 'quality', title: 'Quality scoring & triage', icon: BarChart3,
    blurb: 'Face similarity and the bank triage thresholds.' },
]

/** 🏋️ Training. */
export const TRAINING_GROUPS = [
  { id: 'defaults', title: 'Defaults', icon: SlidersHorizontal,
    blurb: 'The model family new runs start on.' },
  { id: 'masking', title: 'Concept face masking', icon: Drama,
    blurb: 'Masking faces out of concept training.' },
]

/** 💾 Storage. */
export const STORAGE_GROUPS = [
  { id: 'overview', title: 'What lives where', icon: Map,
    blurb: 'Every folder the app writes to, with sizes on demand.' },
  { id: 'locations', title: 'Movable folders', icon: Package,
    blurb: 'The dataset image store and the checkpoint folder.' },
  { id: 'housekeeping', title: 'Cleanup & trash', icon: Trash2,
    blurb: 'The trash and the run image archive.' },
  { id: 'models', title: 'Model files', icon: Box,
    blurb: 'The Hugging Face cache.' },
]

/** Which sections carry groups at all. Scraping, Server, Maintenance and the
 *  Overview keep their flat handful of cards ON PURPOSE: a summary over one
 *  or two cards is navigation for a hallway with one door. */
export const SECTION_GROUPS = {
  engines: ENGINES_GROUPS,
  'local-tools': LOCAL_TOOLS_GROUPS,
  captioning: CAPTIONING_GROUPS,
  training: TRAINING_GROUPS,
  storage: STORAGE_GROUPS,
}

/** The section's groups with the enabled plugins' contributions merged in: a
 *  `settings.group` item `{ id, section, after?, title, blurb, icon, panel }`
 *  lands right after the core group it names (`after`), or at the end. Pure:
 *  the contributions are passed in, so node --test holds the placement. */
export function mergePluginGroups(coreGroups, pluginGroups) {
  const out = [...coreGroups]
  for (const item of pluginGroups) {
    if (!item || typeof item.id !== 'string' || out.some((x) => x.id === item.id)) continue
    // A plugin names no icon component of its own (its descriptor cannot import
    // lucide-react — node resolves a bare package from the importing file's
    // folder, and bundled/ has no node_modules): the core's puzzle piece is
    // the default, and a plugin may still pass one it got from a core module.
    const icon = typeof item.icon === 'string' ? ({ cloud: Cloud }[item.icon] || Puzzle) : (item.icon || Puzzle)
    const g = { ...item, icon }
    const at = g.after ? out.findIndex((x) => x.id === g.after) : -1
    // Every group after a plugin group with the same anchor keeps registration order.
    let insertAt = at < 0 ? out.length : at + 1
    while (insertAt < out.length && out[insertAt].plugin && out[insertAt].after === g.after) insertAt += 1
    out.splice(insertAt, 0, g)
  }
  return out
}

/** Legacy composition helper. General Settings no longer mounts product groups. */
export function withPluginGroups(sectionId, coreGroups) {
  const mine = contributions('settings.group', 'settings').filter((g) => g.section === sectionId && !g.placement)
  return mergePluginGroups(coreGroups, mine)
}

/** The DOM id a group's <details> carries — the TOC and tests address it. */
export function groupDomId(sectionId, groupId) {
  return `settings-group-${sectionId}-${groupId}`
}

const storageKey = (sectionId) => `settingsGroupsOpen.${sectionId}`

/** Which groups start OPEN, read once at mount. Defaults to all collapsed —
 *  the summary at the top of the section is the map, and a wall that opens
 *  fully unfolded is the exact screen this replaces. Storage failures (private
 *  window, blocked site data) mean "all collapsed", never a crash. */
export function readOpenGroups(storage, sectionId) {
  try {
    const raw = storage && storage.getItem(storageKey(sectionId))
    const list = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(list) ? list.filter((v) => typeof v === 'string') : [])
  } catch {
    return new Set()
  }
}

/** Persist one toggle. Write-through and forgiving for the same reasons. */
export function storeGroupToggle(storage, sectionId, groupId, open) {
  try {
    const cur = readOpenGroups(storage, sectionId)
    if (open) cur.add(groupId)
    else cur.delete(groupId)
    storage.setItem(storageKey(sectionId), JSON.stringify([...cur]))
  } catch { /* a private window loses the convenience, not the section */ }
}
