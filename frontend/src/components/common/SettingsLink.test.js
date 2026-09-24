/** Several features are driven by a setting that is discoverable only by knowing it
 * exists — the manual Upscale & improve being the reported case: its strength and
 * instruction are editable, and nothing on the button said so. These links live
 * where the user is ACTING, not on the Settings page they are not on. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const read = (p) => fs.readFileSync(new URL(p, import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const link = read('./SettingsLink.jsx');
const registry = read('../settings/registry.js');
const pluginIds = new Set(['image_upscale', 'scrape', 'cloud_training']);

test('every section a link points at really exists in the settings registry', () => {
  const known = new Set([...registry.matchAll(/id: '([a-z0-9-]+)'/g)].map((m) => m[1]));
  assert.ok(known.size >= 8, 'settings registry did not parse');
  const files = [
    // The lightbox's own improve links moved into KleinImproveNote, which the
    // lightbox AND the grid's bulk toolbar both render — one note, two surfaces.
    '../../../../bundled/image_upscale/frontend/panels/KleinImproveNote.jsx', '../dataset/CaptionToolsBar.jsx',
    '../dataset/TrainingPanel.jsx', "../../../../bundled/scrape/frontend/panels/ConceptSourcesPanel.jsx",
  ];
  let found = 0;
  for (const f of files) {
    for (const m of read(f).matchAll(/<SettingsLink\b[^>]+>/g)) {
      found += 1;
      const plugin = m[0].match(/pluginId="([a-z0-9_]+)"/);
      const section = m[0].match(/section="([a-z0-9-]+)"/);
      assert.ok(plugin || section, `${f}: settings link has no owner`);
      if (plugin) {
        assert.ok(pluginIds.has(plugin[1]), `${f}: unexpected product owner`);
        const manifest = JSON.parse(read(`../../../../bundled/${plugin[1]}/plugin.json`));
        assert.equal(manifest.id, plugin[1]);
      } else assert.ok(known.has(section[1]), `${f}: unknown core settings section`);
    }
  }
  assert.ok(found >= 4, `expected links in every surveyed surface, found ${found}`);
});

test('a settings link never triggers the surface it sits on', () => {
  // These sit on top of tiles and lightboxes whose parents open viewers or start
  // jobs; without this a click would do both.
  assert.match(link, /onClick=\{\(e\) => e\.stopPropagation\(\)\}/);
});

test('the improve link is offered where the improve action is', () => {
  const lightbox = read('../dataset/DatasetLightbox.jsx');
  assert.match(lightbox, /lightboxImproveButtons\(/);
  // The Klein settings prose no longer mounts inline: the ✨ button opens the
  // shared ImproveModal, and the note (with its settings links) is that
  // modal's settings screen — still read in the second before generating,
  // which is the second that matters. Both lightbox hosts mount the SAME
  // modal, so the link travels with the action on every surface.
  const modal = read('../shared/ImproveModal.jsx');
  assert.match(modal, /<KleinImproveNote\b/);
  assert.match(lightbox, /<ImproveModal\b/);
  assert.match(read('../shared/GeneratedImageLightbox.jsx'), /<ImproveModal\b/);
  // The BULK improve is the same action at scale, and it went targetless for a
  // long time: the instruction that spoils one tile spoils the whole selection.
  // A batch panel SHOWS its instruction before launching a lot, so its inline
  // note stays.
  assert.match(read('../dataset/DatasetGrid.jsx'), /<KleinImproveNote\b/);
});

test('the note offers BOTH improve levers — the words and the amount', () => {
  // "Adjust improve strength" was the only pointer for a long time, and it aims
  // at the knobs. The reported complaint (anime turned realistic, Qeeyana on
  // Reddit) is caused by the INSTRUCTION, which had no pointer at all.
  const note = read('../../../../bundled/image_upscale/frontend/panels/KleinImproveNote.jsx');
  assert.match(note, /focus="identity-prompt-klein-improve"/);
  assert.match(note, /focus="klein-improve-strength"/);
});

test('the cloud banner lands on its own plugin settings', () => {
  const page = read('../../../../bundled/cloud_training/frontend/CloudRunsHub.jsx');
  assert.match(page, /navigate\('\/plugins\/cloud_training\/settings'\)/);
  assert.doesNotMatch(page, /navigate\('\/settings'\)/);
});
