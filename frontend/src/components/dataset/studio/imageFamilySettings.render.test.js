import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement, render } from '../../../../tests/support/mountJsx.mjs';
import { MemoryRouter } from 'react-router';

const { default: StudioGenerationSettings } = await import('./StudioGenerationSettings.jsx');
const { default: ComparisonStudio } = await import('./ComparisonStudio.jsx');
const { default: StudioPreflightBanner } = await import('./StudioPreflightBanner.jsx');
const renderComparison = (props) => render(() => createElement(MemoryRouter, null,
  createElement(ComparisonStudio, props)));

test('the negative prompt control renders only when the server says the pipeline applies it', () => {
  const original = globalThis.localStorage;
  globalThis.localStorage = { getItem: (key) => key.endsWith('sec_negative') ? 'true' : null };
  try {
    for (const family of ['anima', 'qwenimage21']) {
      const html = render(StudioGenerationSettings, { family, capabilities: { negative_prompt: true } });
      assert.match(html, /aria-label="Negative prompt"/);
    }
    for (const family of ['flux', 'flux2klein', 'zimage']) {
      const html = render(StudioGenerationSettings, { family, capabilities: { negative_prompt: false } });
      assert.doesNotMatch(html, /aria-label="Negative prompt"/);
    }
  } finally { globalThis.localStorage = original; }
});

test('comparison displays its actual family and selected model defaults', () => {
  const html = renderComparison({
    selection: [
      { dataset_id: 1, checkpoint: 'first.safetensors', family: 'qwenimage21' },
      { dataset_id: 2, checkpoint: 'second.safetensors', family: 'qwenimage21' },
    ],
    runType: 'qwenimage21',
    baseModels: [{ filename: 'qwen-base.safetensors', label: 'Qwen base' }],
    modelDefaults: { 'qwen-base.safetensors': { cfg: 4, steps: 30 } },
    axes: { cfg_choices: [3, 4, 5], steps_choices: [20, 30, 40], default_cfg: 4, default_steps: 30 },
    generationCapabilities: { negative_prompt: true },
  });
  assert.match(html, /Base model \(Qwen-Image 2\.1\)/);
  assert.match(html, /CFG \(multi\) — default 4/);
  assert.match(html, /Steps \(multi\) — default 30/);
  assert.match(html, /Prompt \(optional\)/);
});

test('a model settings failure disables both comparison launch buttons and explains why', () => {
  const html = renderComparison({
    selection: [
      { dataset_id: 1, checkpoint: 'first.safetensors', family: 'anima' },
      { dataset_id: 2, checkpoint: 'second.safetensors', family: 'anima' },
    ], runType: 'anima', settingsError: 'Anima is unavailable on this server.',
  });
  assert.match(html, /Anima is unavailable on this server/);
  const runButtons = html.match(/<button[^>]*>🚀 Run the test<\/button>/g) || [];
  assert.equal(runButtons.length, 2);
  assert.ok(runButtons.every((button) => button.includes('disabled')));
});

test('a configured missing base is shown and blocks comparison instead of selecting an alternative', () => {
  const html = renderComparison({
    selection: [
      { dataset_id: 1, checkpoint: 'first.safetensors', family: 'anima' },
      { dataset_id: 2, checkpoint: 'second.safetensors', family: 'anima' },
    ], runType: 'anima', defaultModel: 'missing-configured.safetensors',
    baseModels: [{ filename: 'another.safetensors', label: 'Another base' }],
  });
  assert.match(html, /Base model unavailable: missing-configured\.safetensors/);
  assert.match(html, /value="missing-configured\.safetensors" selected=""/);
  assert.match(html, /focus=studio-models/);
  assert.doesNotMatch(html, /Download missing models/);
  const runButton = html.match(/<button[^>]*aria-label="Run the test"[^>]*>/)?.[0];
  assert.ok(runButton?.includes('disabled'));
});

test('invalid model configuration blocks comparison even when another model is installed', () => {
  const html = renderComparison({
    selection: [
      { dataset_id: 1, checkpoint: 'first.safetensors', family: 'anima' },
      { dataset_id: 2, checkpoint: 'second.safetensors', family: 'anima' },
    ], runType: 'anima',
    baseModels: [{ filename: 'another.safetensors', label: 'Another base' }],
    generationReadiness: { config_error: 'The selected model is outside the configured folders.' },
  });
  assert.match(html, /The selected model is outside the configured folders/);
  assert.match(html, /focus=studio-models/);
  const runButtons = html.match(/<button[^>]*>🚀 Run the test<\/button>/g) || [];
  assert.equal(runButtons.length, 2);
  assert.ok(runButtons.every((button) => button.includes('disabled')));
});

test('new-family missing files link to their install controls and identify core nodes accurately', () => {
  const html = render(() => createElement(MemoryRouter, null, createElement(StudioPreflightBanner, { missing: {
    family: 'anima', files: [{ path: 'models/diffusion_models/anima.safetensors', kind: 'diffusion model' }],
    nodes: ['AnimaTokenizer'], node_packs: [{ class_type: 'AnimaTokenizer', pack: 'ComfyUI', core: true }],
  } })));
  assert.match(html, /Anima test pipeline/);
  assert.match(html, /focus=studio-models/);
  assert.match(html, /Missing ComfyUI node/);
  assert.doesNotMatch(html, /Missing custom node/);
  assert.match(html, /Fix missing ComfyUI nodes/);
  assert.match(html, /Check nodes again/);
});

test('missing nodes remain actionable when all model files are present', () => {
  const html = renderComparison({
    selection: [{ dataset_id: 1, checkpoint: 'first.safetensors', family: 'qwenimage21' }],
    runType: 'qwenimage21',
    generationReadiness: { label: 'Qwen-Image 2.1', models_ready: true, downloads: [],
      missing_nodes: ['TextEncodeQwenImage21'] },
  });
  assert.match(html, /TextEncodeQwenImage21/);
  assert.match(html, /Fix missing ComfyUI nodes/);
  assert.match(html, /Check nodes again/);
  assert.doesNotMatch(html, /Download missing models/);
  const runButtons = html.match(/<button[^>]*>🚀 Run the test<\/button>/g) || [];
  assert.equal(runButtons.length, 2);
  assert.ok(runButtons.every((button) => button.includes('disabled')));
});

test('missing Qwen files offer in-place downloads and keep generation blocked until all files exist', () => {
  const html = renderComparison({
    selection: [
      { dataset_id: 1, checkpoint: 'first.safetensors', family: 'qwenimage21' },
      { dataset_id: 2, checkpoint: 'second.safetensors', family: 'qwenimage21' },
    ], runType: 'qwenimage21', defaultModel: 'qwen-base.safetensors',
    baseModels: [{ filename: 'qwen-base.safetensors', label: 'Qwen base' }],
    generationReadiness: { label: 'Qwen-Image 2.1', models_ready: false, downloads: [
      { action: 'studio_qwenimage21_text_encoder', label: 'Text encoder',
        filename: 'qwen-encoder.safetensors', size_bytes: 9_000_000_000 },
      { action: 'studio_qwenimage21_vae', label: 'VAE', filename: 'qwen-vae.safetensors' },
    ] },
  });
  assert.match(html, /Download Text encoder/);
  assert.match(html, /Download VAE/);
  assert.match(html, /qwen-encoder.safetensors/);
  assert.match(html, /Check installed files again/);
  const runButtons = html.match(/<button[^>]*>🚀 Run the test<\/button>/g) || [];
  assert.equal(runButtons.length, 2);
  assert.ok(runButtons.every((button) => button.includes('disabled')));
});
