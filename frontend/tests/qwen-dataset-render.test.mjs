import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFileSync } from 'node:fs'
import { parseFragment } from 'parse5'
import { createElement, renderToStaticMarkup, render } from './support/mountJsx.mjs'
import { installRuntimeHost } from './support/runtimeHost.mjs'
import { QWEN_ENGINE } from '../../bundled/qwen_dataset/frontend/lib/engine.js'
import descriptor from '../../bundled/qwen_dataset/frontend/index.js'
import { registerDescriptor, setEnabled } from '../src/plugins/registry.js'

installRuntimeHost({ after })
assert.equal(registerDescriptor(descriptor, { guideOwnership:
  JSON.parse(readFileSync(new URL('../../bundled/qwen_dataset/plugin.json', import.meta.url), 'utf8')).guide_ownership,
}), true)
setEnabled(['qwen_dataset'])
const { default: QwenCard } = await import('../../bundled/qwen_dataset/frontend/panels/QwenCard.jsx')
const { default: QwenSettings } = await import('../../bundled/qwen_dataset/frontend/panels/QwenSettings.jsx')
const { default: QwenPreparation } = await import('../../bundled/qwen_dataset/frontend/panels/QwenPreparation.jsx')
const { MemoryRouter } = await import('react-router')

const card = props => renderToStaticMarkup(createElement(QwenCard, {
  spec: QWEN_ENGINE, checked: false, available: false, generating: null,
  onToggle: () => {}, enabledInSettings: true, caps: {}, ...props,
}))

test('an unprepared engine leaves its settings link outside the disabled checkbox', () => {
  const html = card({})
  const root = parseFragment(html).childNodes[0]
  const button = root.childNodes.find(node => node.tagName === 'button')
  assert.ok(button.attrs.some(attr => attr.name === 'disabled'))
  const findLinks = node => [ ...(node.tagName === 'a' ? [node] : []),
    ...(node.childNodes || []).flatMap(findLinks) ]
  assert.equal(findLinks(button).length, 0)
  assert.equal(findLinks(root).length, 1)
  assert.match(html, /#\/plugins\/qwen_dataset\/settings\?focus=qwen-dataset-preparation/)
  assert.match(html, /Non-commercial/)
  assert.doesNotMatch(html, /NSFW OK/)
})

test('a disabled engine points to its plugin settings engine toggle', () => {
  const html = card({ enabledInSettings: false })
  assert.match(html, /href="#\/plugins\/qwen_dataset\/settings\?focus=plugin-enabled-engines"/)
  assert.match(html, /Enable this engine/)
})

test('settings render the real namespaced values and sampling controls', () => {
  const html = render(MemoryRouter, { children: createElement(QwenSettings, {
    config: { plugins: { qwen_dataset: { steps: 37, cfg: 4.5, reference_resolution: 768, sampler_name: 'euler', scheduler: 'karras' } } },
    configDefaults: { plugins: { qwen_dataset: { steps: 25, cfg: 3 } } },
    setField: () => {}, refreshCaps: () => {},
    caps: { comfyui: { reachable: true, dir_valid: true }, qwen_dataset: { ok: true, missing: [], invalid: [],
      models: { unet: 'qwen_image_2.1_int8_convrot.safetensors', text_encoder: 'qwen3vl_8b_int8_convrot.safetensors', vae: 'qwen_image_2.1_vae_bf16.safetensors' },
    } },
  }) })
  assert.match(html, /id="qwen-dataset-steps"[^>]*value="37"/)
  assert.match(html, /id="qwen-dataset-cfg"[^>]*value="4.5"/)
  assert.match(html, /<option value="euler" selected=""/)
  assert.match(html, /<option value="karras" selected=""/)
})

test('preparation reports model readiness and offers a capability recheck', () => {
  const html = render(MemoryRouter, { children: createElement(QwenPreparation, {
    onDone: () => {}, caps: { comfyui: { reachable: true, dir_valid: true }, qwen_dataset: {
      ok: true, missing: [], invalid: [], models: { unet: 'qwen_image_2.1_int8_convrot.safetensors',
        text_encoder: 'qwen3vl_8b_int8_convrot.safetensors', vae: 'qwen_image_2.1_vae_bf16.safetensors' },
    } },
  }) })
  assert.match(html, /Ready — ComfyUI reports/)
  assert.doesNotMatch(html, />Prepare Qwen3-VL text encoder</)
  assert.match(html, /Re-check preparation/)
})
