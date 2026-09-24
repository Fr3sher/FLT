import { registerBundledDescriptor } from '../../../frontend/tests/support/bundledDescriptors.mjs'
import test from 'node:test'
import assert from 'node:assert/strict'
import { resetRegistry, setEnabled, contributions } from '../../../frontend/src/plugins/registry.js'
import { allHelpTopics } from '../../../frontend/src/help/helpRegistry.js'
import { mlInstallCards } from '../../../frontend/src/components/setup/mlInstallCards.js'
import { deriveCapabilitySummary, deriveSetupSteps } from '../../../frontend/src/hooks/useSetupSteps.js'
import descriptor from '../frontend/index.js'
const { render } = await import('../../../frontend/tests/support/mountJsx.mjs')
const { configureHostRuntime } = await import('../../../frontend/src/plugins/runtimeHost.jsx')
const { publishRuntime } = await import('../../../frontend/src/plugins/loadPlugins.js')
globalThis.window = {}
configureHostRuntime()
publishRuntime()
const { default: ScrapingSection } = await import('../../../frontend/src/components/settings/ScrapingSection.jsx')
const { default: ScrapeSettingsGroup } = await import('../frontend/panels/ScrapeSettingsGroup.jsx')
const props = { config: { klein: { small_image_prompt: '' } }, configDefaults: {},
  secretsPresence: {}, secretInputs: {}, testResults: {}, setField() {}, setSecretInputs() {} }

test('scrape owns its settings, help and installation; disabling removes all its offers', () => {
  resetRegistry()
  assert.equal(registerBundledDescriptor(descriptor), true)
  setEnabled(['scrape'])
  assert.equal(contributions('settings.group').length, 1)
  const html = render(ScrapeSettingsGroup, props)
  for (const id of ['REDDIT_CLIENT_ID', 'PEXELS_API_KEY', 'klein-small-image-prompt', 'scrape-credentials']) {
    assert.ok(html.includes(`id="${id}"`), id)
  }
  assert.ok(mlInstallCards().some((c) => c.action === 'scrape_extras'))
  const scrapeRow = deriveCapabilitySummary({}).find((r) => /Scraping extras/.test(r.label))
  assert.equal(scrapeRow.ok, false)
  assert.equal(scrapeRow.topic, 'setup-quality')
  assert.equal(scrapeRow.plugin, 'scrape', 'the overview links to the owner despite its legacy topic')
  assert.equal(deriveCapabilitySummary({ scrape_deps: true }).find((r) => /Scraping extras/.test(r.label)).ok, true)
  assert.ok(!deriveSetupSteps({}).find((s) => s.id === 'quality').unlocks.includes('Scraping extras (optional)'))
  assert.ok(!mlInstallCards({ includePlugins: false }).some((c) => c.action === 'scrape_extras'))
  assert.ok(allHelpTopics().some((t) => t.id === 'action-scrape-scan'))
  setEnabled([])
  assert.equal(contributions('settings.group').length, 0)
  assert.ok(!mlInstallCards().some((c) => c.action === 'scrape_extras'))
  assert.ok(!deriveCapabilitySummary({}).some((r) => /Scraping extras/.test(r.label)))
  assert.ok(!deriveSetupSteps({}).find((s) => s.id === 'quality').unlocks.includes('Scraping extras (optional)'))
  const disabled = render(ScrapingSection, props)
  assert.ok(disabled.includes('id="CIVITAI_API_KEY"'), 'shared Civitai access remains')
  for (const id of ['REDDIT_CLIENT_ID', 'PEXELS_API_KEY', 'klein-small-image-prompt']) {
    assert.ok(!disabled.includes(`id="${id}"`), id)
  }
  for (const topic of descriptor.help) assert.ok(!allHelpTopics().some((t) => t.id === topic.id), topic.id)
})


test('rescue belongs to the active scraper while core identity prompts remain independently available', async () => {
  const { default: EnginesSection } = await import('../../../frontend/src/components/settings/EnginesSection.jsx')
  const engineProps = { ...props, config: { ...props.config, engines: { enabled: [], default: 'klein' } } }
  resetRegistry()
  assert.equal(registerBundledDescriptor(descriptor), true)
  setEnabled(['scrape'])
  const group = contributions('settings.group').find(g => g.id === 'web-scraping')
  assert.ok(group, 'active scraper contributes its settings door')
  const { default: ContributedSettings } = await group.panel()
  assert.equal(ContributedSettings, ScrapeSettingsGroup)
  const rescue = render(ContributedSettings, props)
  assert.match(rescue, /Klein rescue — small scraped images/)
  assert.match(rescue, /Small-image rescue instruction/)
  assert.match(rescue, /optional Klein Improve plug-in/)
  assert.doesNotMatch(rescue, /Settings ▸ Engines ▸ “Identity, Klein &amp; Krea 2 prompts”/)
  const assertIndependentCore = () => {
    const html = render(EnginesSection, engineProps)
    assert.match(html, /id="identity-prompts"/)
    assert.match(html, /Identity, Klein &amp; Krea 2 prompts \(advanced\)/)
    assert.doesNotMatch(html, /Klein rescue — small scraped images|scraper rescue prompt for small images/)
  }
  assertIndependentCore()
  setEnabled([])
  assert.deepEqual(contributions('settings.group'), [])
  assert.doesNotMatch(render(ScrapingSection, props), /klein-small-image-prompt|Klein rescue/)
  assertIndependentCore()
  resetRegistry()
  assert.deepEqual(contributions('settings.group'), [])
  assert.doesNotMatch(render(ScrapingSection, props), /klein-small-image-prompt|Klein rescue/)
  assertIndependentCore()
})
