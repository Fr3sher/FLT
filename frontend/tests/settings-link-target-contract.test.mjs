/* Contract: a "Settings ▸ … →" pointer lands on what its LABEL promises.

   These links sit where the user is acting (the lightbox, the source picker, the
   training panel). Reported case: "Adjust improve strength →" opened Image
   engines at the top and left the reader to find the strength knobs by eye, one
   long section down. The mechanism to do better already existed — SettingsPage's
   ?focus=<domId> deep link scrolls to one field, opens the collapsed <details>
   around it and rings it — SettingsLink simply never offered it.

   The dangerous failure mode is a target that does NOT exist: ?focus=typo
   scrolls nowhere and says nothing, which is exactly the silent dead-end the
   feature is meant to remove. So every target is checked against the DOM ids the
   Settings sections really render — the same grep-the-source contract the
   help-registry test uses for its own focus anchors.

   The second rule is the honest one: a link may legitimately point at a whole
   section, but never by accident. Section-only links are listed here WITH their
   reason, so a new targetless link fails until someone writes down why. */
import test from 'node:test'
import { readSource } from './support/readSource.mjs'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { settingsLinkHref } from '../src/components/common/settingsLinkHref.js'
import { SETTINGS_SECTIONS } from '../src/components/settings/registry.js'

const read = readSource

// ---- source inventory ------------------------------------------------------

const walk = (dirUrl) => {
  const out = []
  for (const entry of readdirSync(dirUrl, { withFileTypes: true })) {
    const child = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, dirUrl)
    if (entry.isDirectory()) out.push(...walk(child))
    else if (/\.jsx$/.test(entry.name) && !/\.test\.jsx?$/.test(entry.name)) {
      out.push({ path: entry.name, src: readFileSync(fileURLToPath(child), 'utf8') })
    }
  }
  return out
}
const BUNDLED = new URL('../../bundled/', import.meta.url)
const SOURCES = [
  ...walk(new URL('../src/', import.meta.url)),
  ...readdirSync(BUNDLED, { withFileTypes: true }).filter(entry => entry.isDirectory())
    .flatMap(entry => walk(new URL(`${entry.name}/frontend/`, BUNDLED))),
]
// Concrete settings components behind the public owners used by targeted links.
const PLUGIN_SETTINGS = {
  cloud_training: ['../bundled/cloud_training/frontend/settings/CloudTrainingGroup.jsx'],
  image_upscale: ['../bundled/image_upscale/frontend/panels/KleinImproveSettings.jsx',
    '../bundled/image_upscale/frontend/panels/ImproveFinishCard.jsx'],
  scrape: ['../bundled/scrape/frontend/panels/ScrapeSettingsGroup.jsx'],
}

// DOM ids the Settings sections actually render: literal id="…" plus the secret
// field keys (SecretField renders id={f.key}, so the config key IS the DOM id).
const settingsDomIds = (owner = null) => {
  const dir = new URL('../src/components/settings/', import.meta.url)
  let src = ''
  if (owner) {
    assert.ok(PLUGIN_SETTINGS[owner], `Settings source inventory missing for ${owner}`)
    src = PLUGIN_SETTINGS[owner].map(read).join('\n')
  } else {
    for (const f of readdirSync(dir)) if (f.endsWith('.jsx')) src += read(`src/components/settings/${f}`) + '\n'
  }
  const ids = new Set()
  for (const m of src.matchAll(/id="([^"]+)"/g)) ids.add(m[1])
  for (const m of src.matchAll(/\bkey:\s*'([^']+)'/g)) ids.add(m[1])
  return ids
}

const attr = (tag, name) => {
  const literal = tag.match(new RegExp(`\\b${name}="([^"]*)"`))
  if (literal) return { kind: 'literal', value: literal[1] }
  const expr = tag.match(new RegExp(`\\b${name}=\\{([^}]*)\\}`))
  if (expr) return { kind: 'expression', value: expr[1].trim() }
  return null
}

// Every <SettingsLink …> in the app, with where it is and what it aims at.
const usages = () => {
  const out = []
  for (const { path, src } of SOURCES) {
    for (const m of src.matchAll(/<SettingsLink\b([\s\S]*?)>/g)) {
      out.push({ file: path, tag: m[1], section: attr(m[1], 'section'), plugin: attr(m[1], 'pluginId'), focus: attr(m[1], 'focus') })
    }
  }
  return out
}

/* Links that point at a SECTION, on purpose. Each needs a reason: the bar is
   "no single field answers this label", not "nobody got round to it". */
const WITHOUT_TARGET = [
  {
    file: 'ImprovePreparationLinks.jsx', section: 'engine.plugin',
    reason: 'Preparing this engine may need both downloads and options; its whole plugin settings page owns that installation flow.',
  },
  {
    file: 'SetupPage.jsx', section: 's.plugin',
    reason: 'Each readiness item links to the owning plugin preparation page because a recipe can require several downloads and settings.',
  },
  {
    file: 'TrainingPanel.jsx',
    section: 'training',
    reason: '"Defaults & cloud limits" names two things in two cards '
      + '(training-default-family, and the cloud guard-rails card) — focusing '
      + 'either would ring the wrong half for half the readers.',
  },
  {
    file: 'VideoCloudLaunchDialog.jsx',
    section: 'cloud_training',
    reason: 'The link sits under the OFFERS ERROR of the video launch window, and '
      + 'that error has three causes with three different fields (the vast.ai key, '
      + 'the price cap, the fleet limit) — the message names the cause, a single '
      + 'focus would ring the wrong field for two of the three readers.',
  },
]

// ---- the URL itself --------------------------------------------------------

test('a link with no target produces exactly the URL it always did', () => {
  for (const s of SETTINGS_SECTIONS) {
    assert.equal(settingsLinkHref(s.id), `#/settings/${s.id}`)
  }
  // undefined / null / blank are the same "no target" case, never "?focus=".
  for (const empty of [undefined, null, '', '   ']) {
    assert.equal(settingsLinkHref('engines', empty), '#/settings/engines')
  }
})

test('a link with a target produces the ?focus= deep link SettingsPage honours', () => {
  assert.equal(settingsLinkHref('engines', 'klein-improve-strength'),
    '#/settings/engines?focus=klein-improve-strength')
  assert.equal(settingsLinkHref('local-tools', 'aitoolkit-python'),
    '#/settings/local-tools?focus=aitoolkit-python')
})

// ---- targets resolve -------------------------------------------------------

test('every target a SettingsLink uses is a DOM id the Settings really render', () => {
  const ids = settingsDomIds()
  assert.ok(ids.size > 40, 'settings DOM ids did not parse')
  let checked = 0
  for (const u of usages()) {
    if (!u.focus || u.focus.kind !== 'literal') continue
    checked += 1
    const ownerIds = u.plugin?.kind === 'literal' ? settingsDomIds(u.plugin.value) : ids
    assert.ok(ownerIds.has(u.focus.value),
      `${u.file}: SettingsLink focus="${u.focus.value}" is not rendered by the linked settings owner `
      + '— a ?focus= that resolves to nothing scrolls nowhere and reports nothing.')
  }
  assert.ok(checked >= 3, `expected several targeted links, found ${checked}`)
})

test('a target computed at runtime still resolves — the setup verdict case', () => {
  const ids = settingsDomIds()
  const steps = read('src/hooks/useSetupSteps.js')
  const targets = [...steps.matchAll(/settingsFocus:\s*'([^']+)'/g)].map((m) => m[1])
  assert.ok(targets.length >= 1, 'no verdict carries a settingsFocus')
  for (const t of targets) {
    assert.ok(ids.has(t), `useSetupSteps verdict focus "${t}" is not a Settings DOM id`)
  }
  // and the page must actually forward it, or the verdict target is dead weight
  assert.match(read('src/pages/SetupPage.jsx'), /focus=\{verdict\.settingsFocus\}/)
})

// ---- the reported link -----------------------------------------------------

test('the three improve pointers land on the three things they name', () => {
  // All three live in KleinImproveNote now (rendered by the lightbox AND the
  // grid's bulk toolbar) instead of a lone link in the lightbox: the strength
  // knobs never answered "why did my anime turn realistic" — the instruction
  // did. The third arrived with the preset chain: the panel tunes a preset's
  // strengths in place, and BUILDING that preset (adding, removing,
  // reordering) stays one click away, in the card that owns the list.
  const note = read('../bundled/image_upscale/frontend/panels/KleinImproveNote.jsx')
  const tags = [...note.matchAll(/<SettingsLink\b[\s\S]*?>/g)].map((m) => m[0])
  assert.equal(tags.length, 3,
    'the note must offer the instruction, the strength AND the preset list')
  assert.equal(tags.filter(tag => /pluginId="image_upscale"/.test(tag)).length, 2)
  assert.equal(tags.filter(tag => /section="engines"/.test(tag)).length, 1)
  assert.ok(tags.some((t) => /focus="identity-prompt-klein-improve"/.test(t)))
  assert.ok(tags.some((t) => /focus="klein-improve-strength"/.test(t)))
  assert.ok(tags.some((t) => /focus="klein-generation-lora-presets"/.test(t)))
  // Each target is the thing its label names, not a section that contains it.
  const engines = read('src/components/settings/EnginesSection.jsx')
  const improve = read('../bundled/image_upscale/frontend/panels/KleinImproveSettings.jsx')
  assert.match(improve, /id="klein-improve-strength"/)
  assert.match(improve, /id="klein-improve-strength"[^>]*>\s*[\s\S]{0,200}?Upscale &amp; improve — strength/)
  assert.match(improve, /id="identity-prompt-klein-improve"/)
  // The preset CARD is the half the panel does not do: it is where a row is
  // added, removed or reordered, which is why the chain points at it by id
  // rather than at Engines at large.
  assert.match(engines, /id="klein-generation-lora-presets"/)
  assert.match(engines, /title="Klein generation LoRA presets/)
})

// ---- nothing ships targetless by accident ---------------------------------

test('a link without a target is one we decided to leave section-wide', () => {
  const allowed = new Map(WITHOUT_TARGET.map((e) => [`${e.file}:${e.section}`, e]))
  for (const u of usages()) {
    if (u.focus) continue
    const owner = u.plugin || u.section
    assert.ok(owner, `${u.file}: SettingsLink without a section or plugin`)
    const key = `${u.file}:${owner.value}`
    assert.ok(allowed.has(key),
      `${u.file}: SettingsLink section="${owner.value}" carries no focus. Give it the DOM `
      + 'id of the field its label promises, or add it to WITHOUT_TARGET here with the reason.')
    assert.ok(allowed.get(key).reason.length > 40, `${key}: reason too thin to be a decision`)
  }
})

test('the focus mechanism owns the scroll — no second scroll is added alongside', () => {
  // settingsDeepLink already steps aside when a focus is present; targeting more
  // links makes that path hotter, so the rule is asserted here too.
  const decide = read('src/pages/settingsDeepLink.js')
  assert.match(decide, /if \(hasFocus\) return false/)
})


test('plugin-owned settings links preserve their owning route and field', () => {
  for (const [plugin, focus] of [['cloud_training', 'cloud-max-price-per-hour'],
    ['cloud_training', 'HF_CLOUD_TOKEN'], ['image_upscale', 'klein-improve-strength']]) {
    assert.equal(settingsLinkHref('training', focus, plugin), `#/plugins/${plugin}/settings?focus=${focus}`)
    assert.ok(settingsDomIds(plugin).has(focus))
  }
})
