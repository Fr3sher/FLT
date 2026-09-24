import assert from 'node:assert/strict';
import test from 'node:test';
import { buildGeneratePayload, writerContext } from '../frontend/studio/video/videoStudioApi.js';
import { generateLabel, queueClips } from '../frontend/studio/video/videoStartFrames.js';
import { referenceInstallPlan } from '../frontend/studio/video/videoReferenceInstall.js';
import { readFileSync } from 'node:fs';
import { ASPECTS, REFERENCE_DEFAULTS, cutBody, cutDefaultDuration, cutInterval, moveReference, readReferenceDraft, referenceDescriptors, referenceFormat, referenceFormatSize,
  referencePayload, referenceUrl, replaceReference, selectReferenceFormat, remapReferencePrompt, taggedReferences, writeReferenceDraft } from '../frontend/studio/video/videoReferences.js';

const refs = [
  { kind: 'audio', name: 'voice.wav', role: 'voice' },
  { kind: 'video', name: 'motion.mp4', role: 'movement', include_audio: true },
  { kind: 'image', name: 'alice.png', role: 'person' },
  { kind: 'image', name: 'coat.png', role: 'coat' },
];

test('one video sets output format without changing reference roles, order or audio', () => {
  const original = [...refs, { kind: 'video', name: 'portrait.mp4', role: 'scene', source_width: 1080, source_height: 1920 }];
  const first = selectReferenceFormat(original, 'motion.mp4', true);
  const second = selectReferenceFormat(first, 'portrait.mp4', true);
  assert.equal(referenceFormat(first).name, 'motion.mp4');
  assert.equal(referenceFormat(second).name, 'portrait.mp4');
  assert.equal(second.filter((r) => r.use_format === true).length, 1);
  assert.deepEqual(second.map((r) => [r.name, r.role, r.include_audio]), original.map((r) => [r.name, r.role, r.include_audio]));
  assert.equal(referenceFormat(original), null);
  assert.equal(referenceFormat(selectReferenceFormat(second, 'portrait.mp4', false)), null);
  assert.equal(referenceFormat(second.filter((r) => r.name !== 'portrait.mp4')), null);
  assert.equal(referenceFormat(moveReference(second, 'portrait.mp4', -1)).tag, '<Video 1>');
});

test('format selection, original dimensions and manual shape survive reload and history descriptors', () => {
  const data = new Map();
  const storage = { getItem: (key) => data.get(key), setItem: (key, value) => data.set(key, value) };
  const video = { kind: 'video', name: 'wide.mp4', use_format: true,
    width: 640, height: 352, source_width: 640, source_height: 360 };
  writeReferenceDraft({ references: [video], settings: { aspect: 'square', megapixels: 0.7 } }, storage);
  const restored = readReferenceDraft(storage);
  assert.equal(referenceFormat(restored.references).name, video.name);
  assert.equal(referenceFormatSize(restored.references[0]), '640 × 360');
  assert.equal(referenceFormat(referenceDescriptors([video])).use_format, true, 'Reuse receives the same selection');
  assert.equal(restored.settings.aspect, 'square');
  assert.equal(restored.settings.megapixels, 0.7);
  assert.equal(referenceFormatSize({ width: 640, height: 352 }), '', 'staged dimensions are not presented as original');
});

test('generate sends only the selected video format flag and keeps resolution and manual fallback', () => {
  const selected = [...refs, { kind: 'video', name: 'portrait.mp4', use_format: true,
    source_width: 1080, source_height: 1920 }];
  const body = buildGeneratePayload({ mode: 'ref2va', references: referencePayload(selected),
    aspect: 'square', megapixels: 0.7 });
  assert.equal(body.references.filter((r) => r.use_format).length, 1);
  assert.equal(body.references.at(-1).use_format, true);
  assert.equal(body.references.at(-1).source_width, undefined, 'server owns source dimensions');
  assert.equal(body.aspect, 'square');
  assert.equal(body.megapixels, 0.7);
  assert.ok(referencePayload(refs).every((r) => !Object.hasOwn(r, 'use_format')), 'legacy payload unchanged');
});

test('tag ordinals group media and count video sound before standalone audio', () => {
  assert.deepEqual(taggedReferences(refs).map((r) => [r.name, r.tag, r.audioTag]), [
    ['alice.png', '<Picture 1>', null], ['coat.png', '<Picture 2>', null],
    ['motion.mp4', '<Video 1>', '<Audio 1>'], ['voice.wav', '<Audio 2>', null],
  ]);
  const silent = refs.map((r) => ({ ...r, include_audio: false }));
  assert.equal(taggedReferences(silent).at(-1).tag, '<Audio 1>');
});

test('reorder swaps tags atomically, keeps roles and refuses crossing media types', () => {
  const moved = moveReference(refs, 'coat.png', -1);
  assert.equal(moved[2].name, 'coat.png');
  assert.equal(remapReferencePrompt('<Picture 1> wears <Picture 2>; <Picture 1> speaks.', refs, moved),
    '<Picture 2> wears <Picture 1>; <Picture 2> speaks.');
  assert.deepEqual(moveReference(refs, 'motion.mp4', -1), refs);
  assert.equal(refs[2].name, 'alice.png', 'input remains unchanged');
});

test('removal marks its old prompt mentions while shifting the remaining references', () => {
  assert.equal(remapReferencePrompt('<Picture 1> and <Picture 2>', refs, refs.filter((r) => r.name !== 'alice.png')),
    '[removed Picture 1] and <Picture 1>');
  assert.equal(remapReferencePrompt('<Audio 1> then <Audio 2>', refs, refs.map((r) => ({ ...r, include_audio: false }))),
    '[removed Audio 1] then <Audio 1>');
});

test('reference generation sends all media and guides, and excludes stale FL2V acceleration patches', () => {
  const body = buildGeneratePayload({ mode: 'ref2va', references: referencePayload(refs),
    prompt: '  <Picture 1> follows <Video 1>  ', refBase: 'light', refImageSize: 'max',
    image: 'first.png', endImage: 'last.png', aspect: 'portrait', accel: 'ref8', steps: 8,
    turbo: true, eros: true, light: true, sparse: 'max', latentUpscale: true, enhance: true });
  assert.equal(body.mode, 'ref2va');
  assert.equal(body.accel, 'ref8');
  assert.deepEqual(body.references, referencePayload(refs));
  assert.equal(body.ref_base, 'light'); assert.equal(body.ref_image_size, 'max');
  assert.equal(body.image, 'first.png'); assert.equal(body.end_image, 'last.png');
  assert.equal(body.aspect, 'portrait'); assert.equal(body.enhance, true);
  assert.equal(body.sparse, 'max');
  for (const key of ['turbo', 'eros', 'light', 'latent_upscale']) assert.equal(body[key], undefined);
  assert.equal(buildGeneratePayload({ mode: 'ref2va', accel: 'turbo', turbo: true }).accel, '');
});

test('reference sparse attention is opt-in, persisted separately and sent for every reference acceleration', () => {
  const data = new Map();
  const storage = { getItem: (key) => data.get(key), setItem: (key, value) => data.set(key, value) };
  assert.equal(readReferenceDraft(storage).settings.sparse, '');
  for (const accel of ['', 'ref4', 'ref8']) {
    writeReferenceDraft({ settings: { accel, sparse: 'conservative' } }, storage);
    const restored = readReferenceDraft(storage).settings;
    assert.equal(restored.sparse, 'conservative');
    assert.equal(buildGeneratePayload({ mode: 'ref2va', ...restored }).sparse, 'conservative');
    assert.equal(buildGeneratePayload({ mode: 'ref2va', ...restored, sparse: '' }).sparse, undefined);
  }
});

test('VDN Reference Setup installs its stage without the LightX adapter helper', () => {
  const status = { missing_weights: [
    { action: 'h3_ref_base_light' }, { action: 'h3_vdn_stage' }, { action: 'h3_ref_turbo_8_lora' },
  ], missing_nodes: [{ action: 'h3_reference_nodes' }] };
  assert.deepEqual(referenceInstallPlan(status, 'light', 'vdn'), ['h3_ref_base_light', 'h3_vdn_stage']);
});

test('VDN reference persists, retains the continuation and emits only compatible attention', () => {
  const data = new Map();
  const storage = { getItem: (key) => data.get(key), setItem: (key, value) => data.set(key, value) };
  const pictures = [1, 2, 3].map((n) => ({ kind: 'image', name: `reference-${n}.png`,
    role: n === 3 ? 'first frame of the video' : `creature ${n}` }));
  writeReferenceDraft({ active: true, references: pictures,
    settings: { base: 'light', accel: 'vdn', sparse: 'max', steps: 12 } }, storage);
  const restored = readReferenceDraft(storage);
  assert.equal(restored.settings.accel, 'vdn');
  assert.equal(restored.settings.sparse, 'max');
  const body = buildGeneratePayload({ mode: 'ref2va', ...restored.settings,
    refBase: restored.settings.base, references: referencePayload(restored.references),
    prompt: '<Picture 1> moves toward <Picture 2> from <Picture 3>.',
    image: 'seam.png', continues: 42, turbo: true });
  assert.equal(body.accel, 'vdn');
  assert.equal(body.ref_base, 'light');
  assert.equal(body.steps, 12);
  assert.equal(body.image, 'seam.png');
  assert.equal(body.continues, 42);
  assert.deepEqual(body.references, pictures);
  assert.equal(body.sparse, undefined);
  assert.equal(body.turbo, undefined);
});

test('all references produce one clip, irrespective of the former I2V frame strip', async () => {
  const bodies = [];
  const result = await queueClips([null], { mode: 'ref2va', references: referencePayload(refs),
    prompt: 'move', accel: 'ref4', seed: 10 }, async (body) => { bodies.push(body); return { seed: 10 }; });
  assert.equal(result.queued.length, 1); assert.equal(bodies[0].references.length, 4);
  assert.equal(generateLabel({ mode: 'ref2va', count: 9 }), 'Generate clip');
});

test('Auto and Enrich get references, roles, selected base and separate temporal guides', () => {
  const context = writerContext({ mode: 'ref2va', references: referencePayload(refs),
    refBase: 'eros', refImageSize: 'max', endFrame: { image: 'end.png' } });
  assert.equal(context.mode, 'ref2va'); assert.equal(context.ref_base, 'eros');
  assert.equal(context.ref_image_size, 'max'); assert.equal(context.end_image, 'end.png');
  assert.equal(context.references[1].include_audio, true);
  assert.equal(context.references[2].role, 'person');
});

test('reference draft survives storage and retains playback metadata without preview blobs', () => {
  const data = new Map();
  const storage = { getItem: (key) => data.get(key), setItem: (key, v) => data.set(key, v) };
  writeReferenceDraft({ active: true, references: [{ ...refs[1], duration: 7, has_audio: true, preview: 'blob:old' }],
    settings: { base: 'light', accel: 'ref8', imageSize: 'max', frames: 124, aspect: 'portrait' } }, storage);
  const restored = readReferenceDraft(storage);
  assert.equal(restored.active, true); assert.equal(restored.settings.accel, 'ref8');
  assert.equal(restored.settings.aspect, 'portrait'); assert.equal(restored.references[0].has_audio, true);
  assert.equal(restored.references[0].preview, undefined);
  assert.equal(restored.references[0].duration, 7);
  const broken = { getItem: () => { throw Error('denied'); }, setItem: () => { throw Error('denied'); } };
  assert.equal(readReferenceDraft(broken).active, false);
  assert.doesNotThrow(() => writeReferenceDraft({ references: refs }, broken));
  assert.equal(referenceUrl('a&b.wav'), '/api/video-studio/reference?name=a%26b.wav');
});

test('Setup downloads only the chosen base, acceleration and missing shared dependencies', () => {
  const status = { missing_weights: ['h3_ref_base', 'h3_ref_base_light', 'h3_ref_base_eros',
    'h3_ref_turbo_4_lora', 'h3_ref_turbo_8_lora', 'h3_text_encoder'].map((action) => ({ action })),
  missing_nodes: ['MiniMaxH3ReferenceToVideo', 'LDSMiniMaxH3ReferenceLoRA'] };
  assert.deepEqual(referenceInstallPlan(status, 'light', 'ref8'),
    ['h3_reference_nodes', 'h3_ref_base_light', 'h3_ref_turbo_8_lora', 'h3_text_encoder']);
  assert.deepEqual(referenceInstallPlan(status, 'official', ''), ['h3_ref_base', 'h3_text_encoder']);
  assert.deepEqual(referenceInstallPlan({ missing_weights: [], missing_nodes: [] }, 'eros', 'ref4'), []);
});


// --- ✂ cut a reference video (2026-09-06) ------------------------------------------

test('a cut interval is checked like a library excerpt and never the whole video', () => {
  const video = { kind: 'video', name: 'long.mp4', duration: 15 };
  assert.equal(cutInterval(video, '2', '5').error, '');
  assert.deepEqual(cutInterval(video, '2', '5'), { start: 2, duration: 5, error: '' });
  assert.match(cutInterval(video, '', '5').error, /start time/);
  assert.match(cutInterval(video, '-1', '5').error, /start time/);
  assert.match(cutInterval(video, '0', '1').error, /2–15 seconds/);
  assert.match(cutInterval(video, '0', '16').error, /2–15 seconds/);
  assert.match(cutInterval(video, '12', '5').error, /past the end/);
  assert.match(cutInterval(video, '0', '15').error, /shorter interval than the whole/);
  assert.match(cutInterval({ kind: 'video', name: 'x.mp4' }, '0', '5').error, /could not be read/);
});

test('the cut body names the staged copy and carries the role and the audio choice', () => {
  const video = { kind: 'video', name: 'long.mp4', duration: 15, role: 'dance', include_audio: true, has_audio: true };
  assert.deepEqual(cutBody(video, '2', '5'), { kind: 'video', cut_from: 'long.mp4', start_seconds: 2, duration_seconds: 5, role: 'dance', include_audio: true });
  assert.equal(cutBody({ ...video, has_audio: false }, 2, 5).include_audio, false);
  assert.equal(cutBody({ kind: 'video', name: 'l.mp4' }, 2, 5).role, '');
});

test('the cut swaps in place: same position, role, format choice and library key', () => {
  const list = [
    { kind: 'image', name: 'a.png', role: 'person' },
    { kind: 'video', name: 'long.mp4', role: 'dance', use_format: true, key: 'lib:1', include_audio: true },
    { kind: 'video', name: 'other.mp4', role: 'camera' },
  ];
  const out = replaceReference(list, 'long.mp4', { kind: 'video', name: 'short.mp4', duration: 5, cut_from: 'long.mp4', role: 'dance', include_audio: true, has_audio: true });
  assert.deepEqual(out.map((r) => r.name), ['a.png', 'short.mp4', 'other.mp4']);
  assert.equal(out[1].role, 'dance');
  assert.equal(out[1].use_format, true);
  assert.equal(out[1].key, 'lib:1');
  assert.equal(out[1].cut_from, 'long.mp4');
  assert.equal(out[2].use_format, undefined);
  // The tags follow the position, so the prompt keeps naming <Video 1>.
  assert.equal(taggedReferences(out).find((r) => r.name === 'short.mp4').tag, '<Video 1>');
});

test('the panel offers the cut on every video card, with the library excerpt words', () => {
  const src = readFileSync(new URL('../frontend/studio/video/VideoReferencesPanel.jsx', import.meta.url), 'utf8');
  assert.match(src, /function ReferenceCut\(/);
  assert.match(src, /data-testid="reference-cut-open"/);
  assert.match(src, /data-testid="reference-cut-apply"/);
  assert.match(src, /Start · seconds/);
  assert.match(src, /Duration · seconds/);
  assert.match(src, /<ReferenceCut key=\{r\.name\} reference=\{r\} clipSeconds=\{clipSeconds\} disabled=\{busy \|\| disabled\} onCut=/);
  assert.match(src, /postJson\(referenceUrl\(\), cutBody\(reference, start, duration\)\)/);
  assert.match(src, /replaceReference\(list, reference\.name, r\.reference\)/);
  // The threshold is said where the cut is made: the render reads a reference
  // video up to the clip's length, only a shorter cut lightens it (refuted
  // claim of 2026-09-06: "shorter is faster" without the condition).
  assert.match(src, /a cut shorter than that lightens the render, a longer one changes nothing/);
  assert.match(src, /Only a cut shorter than the clip \(\$\{clipSeconds\.toFixed\(1\)\} s\) lightens the render/);
  assert.doesNotMatch(src, /Shorter is faster/);
});


test('the prompt keeps naming <Video 1> and <Audio 1> through a cut, and a cut of a cut', () => {
  // Review of 2026-09-06: the hook remaps the prompt by NAME on every change
  // of the list, and a cut is a new name — the tag became [removed Video 1].
  const before = [
    { kind: 'image', name: 'a.png', role: 'person' },
    { kind: 'video', name: 'long.mp4', role: 'dance', include_audio: true, has_audio: true },
    { kind: 'video', name: 'other.mp4', role: 'camera' },
  ];
  const prompt = '<Picture 1> does the <Video 1> dance with <Audio 1>, camera as <Video 2>';
  const once = replaceReference(before, 'long.mp4', { kind: 'video', name: 'cut-1.mp4', cut_from: 'long.mp4', include_audio: true, has_audio: true, duration: 5 });
  assert.equal(remapReferencePrompt(prompt, before, once), prompt);
  const twice = replaceReference(once, 'cut-1.mp4', { kind: 'video', name: 'cut-2.mp4', cut_from: 'cut-1.mp4', include_audio: true, has_audio: true, duration: 3 });
  assert.equal(remapReferencePrompt(prompt, once, twice), prompt);
  // A real removal still marks the tag.
  assert.equal(remapReferencePrompt(prompt, once, once.filter((r) => r.name !== 'cut-1.mp4')),
    '<Picture 1> does the [removed Video 1] dance with [removed Audio 1], camera as <Video 1>');
});

test('the draft and a reuse keep what a video was cut from', () => {
  const list = [{ kind: 'video', name: 'cut-1.mp4', role: 'dance', include_audio: false, has_audio: true, duration: 5,
    cut_from: 'long.mp4', cut_source_duration: 15, width: 432, height: 768 }];
  const store = new Map();
  const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  writeReferenceDraft({ active: true, references: list, settings: {}, firstFrame: null, endFrame: null }, storage);
  const back = readReferenceDraft(storage).references[0];
  assert.equal(back.cut_from, 'long.mp4');
  assert.equal(back.cut_source_duration, 15);
  assert.equal(referenceDescriptors([{ kind: 'video', name: 'v.mp4', role: '', duration: 4 }])[0].cut_from, undefined);
});

test('the cut block opens on a valid interval, never the whole video', () => {
  for (const total of [15, 14.958, 7.292, 5.2, 4, 2.2, 2.05]) {
    const d = cutDefaultDuration(total);
    assert.equal(cutInterval({ kind: 'video', name: 'v.mp4', duration: total }, '0', String(d)).error, '', `total ${total} -> ${d}`);
  }
  assert.equal(cutDefaultDuration(15), 5);
  assert.equal(cutDefaultDuration(4), 3.5);
  assert.equal(cutDefaultDuration(2.2), 2);
});

test('an armed continuation survives the reload the draft is kept for', () => {
  const data = new Map()
  const storage = { getItem: (key) => data.get(key), setItem: (key, value) => data.set(key, value) }
  // ⏭ Continue on a References clip arms the first frame guide. The draft is
  // what a reload gives back, so the clip that guide continues has to be in
  // it — a guide that came back WITHOUT it would render a lookalike joined to
  // nothing, which is the failure this whole feature is about (2026-09-07).
  writeReferenceDraft({ active: true, references: [{ kind: 'image', name: 'a.png', role: '' }],
    settings: { aspect: 'portrait' },
    firstFrame: { image: 'lds_vstudio_0123456789.png', continues: 135 } }, storage)
  const back = readReferenceDraft(storage)
  assert.deepEqual(back.firstFrame, { image: 'lds_vstudio_0123456789.png', continues: 135 })
  assert.equal(back.active, true)
  // And a guide with no picture is no guide, continuation or not.
  writeReferenceDraft({ firstFrame: { continues: 135 } }, storage)
  assert.equal(readReferenceDraft(storage).firstFrame, null)
})

test("a shape the select does not offer never reaches the control, saved or restored", () => {
  const data = new Map()
  const storage = { getItem: (key) => data.get(key), setItem: (key, value) => data.set(key, value) }
  // 'auto' is the column default and what an unknown value is normalised to,
  // so ref2va rows carry it. Restored as-is, the <select> shows NOTHING —
  // measured on a render, 2026-09-07 — and the launch goes out 16:9 anyway.
  writeReferenceDraft({ settings: { aspect: 'auto' } }, storage)
  assert.equal(readReferenceDraft(storage).settings.aspect, REFERENCE_DEFAULTS.aspect)
  writeReferenceDraft({ settings: { aspect: 'portrait' } }, storage)
  assert.equal(readReferenceDraft(storage).settings.aspect, 'portrait', 'a real one is kept')
  assert.deepEqual(ASPECTS, ['landscape', 'portrait', 'square'])
  // ↻ Reuse takes the same route through the same list, and a JOINED clip's
  // frame count (the FILE's: parent + part − 1) never becomes a dial again.
  const hook = readFileSync(new URL('../frontend/studio/video/useVideoReferences.js', import.meta.url), 'utf8')
  assert.match(hook, /aspect: ASPECTS\.includes\(clip\.aspect\) \? clip\.aspect : d\.settings\.aspect/)
  assert.match(hook, /frames: clip\.joined \? d\.settings\.frames : \(clip\.frames \|\| d\.settings\.frames\)/)
})
