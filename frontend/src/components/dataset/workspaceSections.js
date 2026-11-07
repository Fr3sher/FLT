// Data-driven section list for the dataset workspace sidebar — same pattern as
// the Settings rail (components/settings/registry.js): stable ids (deep-linked
// through ?section=), icon + title for the nav, and a mono eyebrow tag + short
// description for the section header. The list is identical for every dataset
// kind; only the CONTENT of a section branches on kind (e.g. "Add images" is
// reference+generation for a character, scraping+import for a concept/style).

import { ArrowLeftRight, Camera, Globe, GraduationCap, Images, Package, PenLine, SlidersHorizontal, Sparkles } from 'lucide-react';
import { contributions } from '../../plugins/registry.js';
export const WORKSPACE_SECTIONS = [
  // "Add images" sits above "Images" on purpose: the rail mirrors the real
  // workflow order (build the set first, then review it) — matching the
  // guided PROGRESS list. The default landing section stays 'images'
  // (workspaceNavigation.js), which is position-independent.
  { id: 'add', title: 'Add images', icon: Camera, eyebrow: 'build',
    description: 'Generate AI variations from the reference and import photos.',
    conceptDescription: 'Import images to build your training dataset.',
    panels: [
      { id: 'reference', title: 'Reference photo', targetId: 'ds-add-reference', when: 'character' },
      { id: 'generate', title: 'Generate variations', targetId: 'ds-add-generate', when: 'character' },
      { id: 'import', title: 'Import photos', targetId: 'ds-add-import', when: 'always' },
    ] },
  { id: 'images', title: 'Images', icon: Images, eyebrow: 'overview',
    description: 'Everything in the dataset — keep ✓ the good shots, reject ✕ the rest, edit a caption right on its tile.',
    panels: [
      { id: 'review', title: 'Review images', targetId: 'ds-images-review', when: 'always' },
      { id: 'bulk', title: 'Bulk actions', targetId: 'ds-images-bulk', when: 'hasSelectableImages' },
    ] },
  { id: 'scrape', title: 'Scrape', icon: Globe, eyebrow: 'build', slot: 'sources.panel',
    description: 'Scan a gallery URL, pick the images you want, and import them full-frame — crop each one afterwards on its tile.',
    panels: [
      { id: 'scan', title: 'Scan a gallery', targetId: 'ds-scrape-scan', when: 'always',
        focusSelector: 'input[type="url"]' },
    ] },
  { id: 'curation', title: 'Curation', icon: Sparkles, eyebrow: 'quality',
    // "kept images" was true of every pass here until face resemblance started
    // scoring the undecided pile too — which is the whole point of scoring it.
    description: 'Quality passes — face resemblance (kept + still undecided), watermark find & clean, cleanup.',
    panels: [
      { id: 'small-image-rescue', title: 'Klein rescue review', targetId: 'ds-curation-small-image-rescue', when: 'smallImageRescue' },
      { id: 'face-analysis', title: 'Face analysis', targetId: 'ds-curation-face-analysis', when: 'character' },
      { id: 'watermarks', title: 'Watermarks', targetId: 'ds-curation-watermarks', when: 'always' },
      { id: 'review-flagged', title: 'Review flagged', targetId: 'ds-curation-review-flagged', when: 'watermarkDetected' },
      { id: 'reject-flagged', title: 'Reject all flagged', targetId: 'ds-curation-reject-flagged', when: 'watermarkRejectable' },
      { id: 'rejected-cleanup', title: 'Rejected cleanup', targetId: 'ds-curation-rejected-cleanup', when: 'unused' },
    ] },
  { id: 'captions', title: 'Captions', icon: PenLine, eyebrow: 'text',
    description: 'Captions are what training reads each image by — generate them, watch for leaks, edit in bulk.',
    panels: [
      { id: 'generate', title: 'Generate captions', targetId: 'ds-captions-generate', when: 'always' },
      { id: 'leak-review', title: 'Leak review', targetId: 'ds-captions-leak-review', when: 'leakReview', reveal: 'caption-leak' },
      // The bench sits between "is my text leaking?" and "rewrite it in bulk",
      // because that is when it is useful: try the configs on ONE image before
      // paying for a pass over the whole set. Gated on kept images, not on
      // captioned ones — the Lab GENERATES, it does not compare stored text.
      { id: 'lab', title: 'Caption Lab', targetId: 'ds-captions-lab', when: 'hasKeptImages' },
      { id: 'tools', title: 'Caption tools', targetId: 'ds-captions-tools', when: 'hasCaptionedKept', reveal: 'caption-tools' },
    ] },
  // The plugins' ways out (a publisher's row) are rows too: contributed to
  // `export.action`, appended by sectionPanels() with their own `when(context)`
  // predicate — the rail, the deep links and the section all read the same list.
  { id: 'export', title: 'Import & export', icon: ArrowLeftRight, eyebrow: 'data', rowSlot: 'export.action',
    description: 'Merge an existing dataset in — or get this one out: training ZIP, bank, portable backup, and what your plugins add.',
    panels: [
      { id: 'import', title: 'Import dataset', targetId: 'ds-export-import', when: 'always' },
      { id: 'training-zip', title: 'Export training ZIP', targetId: 'ds-export-training-zip', when: 'always' },
      { id: 'to-bank', title: 'Import to bank', targetId: 'ds-export-to-bank', when: 'always' },
      { id: 'backup', title: 'Portable backup', targetId: 'ds-export-backup', when: 'always' },
    ] },
  { id: 'training', title: 'Training', icon: GraduationCap, eyebrow: 'train',
    description: 'Turn the kept and captioned images into a LoRA.',
    panels: [
      { id: 'launch', title: 'Training status & launch', targetId: 'ds-training-launch', when: 'always' },
      { id: 'advanced', title: 'Advanced options', targetId: 'ds-training-advanced', when: 'trainingVisible', reveal: 'training-advanced' },
      { id: 'queue', title: 'Training queue', targetId: 'ds-training-queue', when: 'trainingQueue' },
    ] },
  { id: 'checkpoints', title: 'Checkpoints & LoRAs', icon: Package, eyebrow: 'results',
    description: 'Review training saves, pick an epoch, import LoRAs into ComfyUI, and clean up old files.',
    panels: [
      { id: 'manager', title: 'Checkpoint manager', targetId: 'ds-checkpoints-manager', when: 'trainingVisible' },
    ] },
  { id: 'studio', title: 'Studio', icon: SlidersHorizontal, eyebrow: 'test',
    description: 'Test the trained LoRA with saved winning settings in the dedicated Studio.',
    panels: [
      { id: 'launcher', title: 'LoRA testing studio', targetId: 'ds-studio-launcher', when: 'studioVisible' },
    ] },
];

// Which section hosts each jump anchor (gf-*). Consumed by jumpTo: switch to
// the section first, then scroll to the anchor inside it. Covers the guided
// checklist targets AND the backend preflight "Fix →" targets (gf-generate,
// gf-images — see lora_training.py).
export const SECTION_FOR_TARGET = {
  'gf-reference': 'add',
  'gf-generate': 'add',
  'gf-images': 'images',
  'gf-curation': 'curation',
  'gf-captions': 'captions',
  'gf-export': 'export',
  'gf-training': 'training',
  'gf-checkpoints': 'checkpoints',
  'gf-studio': 'studio',
};

export function isWorkspaceSection(id) {
  return WORKSPACE_SECTIONS.some((s) => s.id === id);
}

/** A plugin's contribution to a section's row slot, as a panel row: its
 *  `when` is the contribution's own predicate over the navigation context. */
function pluginRow(item) {
  return {
    id: item.id, title: item.title, targetId: item.targetId, when: item.when,
    summary: item.summary, plugin: item.plugin,
  };
}

/** The rows of a section: the core's, then what enabled plugins contribute to
 *  its row slot (read at call time — the registry is fixed after boot). */
export function sectionPanels(section) {
  if (!section) return [];
  if (!section.rowSlot) return section.panels;
  return [...section.panels, ...contributions(section.rowSlot, 'dataset').map(pluginRow)];
}
