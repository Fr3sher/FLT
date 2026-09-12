import { engineCatalog } from '../../engines/catalog.js'
import { capabilityDestination, deriveSetupSteps } from '../../hooks/useSetupSteps.js'
import { pluginActive, pluginDesired } from '../../plugins/lifecycle.js'
import { pluginSettingsPath } from '../../pages/pluginSettings.js'

export const SETUP_GOALS = [
  { id: 'dataset', title: 'Prepare a dataset', description: 'Import your images, organize them and edit captions. No extra download needed.', icon: 'images' },
  { id: 'captions', title: 'Automatically caption images', description: 'Let a local AI describe your images. We will help connect it and choose a vision model.', icon: 'captions' },
  { id: 'images', title: 'Generate images', description: 'Choose an image engine, then prepare only the tools and models it needs.', icon: 'generate' },
  { id: 'plugins', title: 'Create videos & add tools', description: 'Choose a plugin from the Store, then follow its activation and preparation steps.', icon: 'plugins' },
]

const ID = /^[a-z][a-z0-9_-]{0,63}(\.[a-z][a-z0-9_-]{0,63})?$/
export function normalizeJourney(value) {
  if (!value || !SETUP_GOALS.some(goal => goal.id === value.goal)) return null
  const result = { goal: value.goal }
  for (const key of ['plugin', 'engine']) {
    if (typeof value[key] === 'string' && ID.test(value[key])) result[key] = value[key]
  }
  if (typeof value.capability === 'string' && value.capability.length <= 200) result.capability = value.capability
  return result
}

export function journeyPath(value) {
  const journey = normalizeJourney(value)
  return journey ? '/setup?' + new URLSearchParams(journey) : '/setup'
}

export function journeyToolPath(step, value) {
  const params = new URLSearchParams(normalizeJourney(value) || {})
  params.set('step', step)
  return '/setup?' + params
}

export function localJourneyPath(value) {
  return typeof value === 'string' && /^\/(?!\/)[^\s\\\u0000-\u001f]*$/.test(value) ? value : null
}

export function journeyProducts(catalog, installed = []) {
  const products = new Map()
  for (const product of catalog?.products || []) {
    const release = product.recommended || product.releases?.[0]
    if (release?.manifest) products.set(product.id, { id: product.id, name: release.manifest.name,
      description: release.manifest.description, experience: release.manifest.experience,
      issues: release.compatibility_issues || [], price: release.price, installed: false })
  }
  for (const plugin of installed) {
    products.set(plugin.id, { ...products.get(plugin.id), id: plugin.id, name: plugin.name,
      description: plugin.description, experience: plugin.package_contract?.experience,
      installed: true })
  }
  return [...products.values()]
}

const action = (label, to) => ({ label, to })
const row = (id, title, ready, description, next) => ({ id, title, ready, description, action: next })
const finish = (title, description, to, label) => ({ title, description, links: [action(label, to)] })

function pluginLifecycle(plugin, product, journey) {
  const installedPath = '/plugins?tab=installed&plugin=' + encodeURIComponent(journey.plugin || '')
  const discoverPath = '/plugins?tab=discover&plugin=' + encodeURIComponent(journey.plugin || '')
  const activationReady = !!plugin && pluginActive(plugin) && pluginDesired(plugin) && !plugin.pending_action
  const rows = [
    row('package', 'Install ' + (product?.name || plugin?.name || 'the plugin'), !!plugin,
      plugin ? 'The package has been downloaded. Activation and its tools are checked separately.'
        : 'Review the plugin, its requirements and any price in the Store, then confirm the installation plan.',
      action('Review plugin in the Store', discoverPath)),
    row('activation', 'Activate the plugin', activationReady,
      activationReady ? 'The plugin is active in this running LDS session.'
        : plugin?.pending_action ? 'A plugin change is waiting. Open My plugins and choose Apply and restart. Your setup plan stays saved in this browser.'
          : !plugin ? 'LDS will need to restart once the plugin installation is prepared.'
            : plugin.error || 'Open My plugins to turn on the plugin, apply changes or repair its installation.',
      action(plugin?.pending_action ? 'Apply changes in My plugins' : 'Open My plugins', installedPath)),
  ]
  if (plugin?.environment) rows.push(row('environment', 'Prepare the plugin’s tools', plugin.environment.ready === true,
    plugin.environment.ready ? 'The plugin’s software dependencies are ready.'
      : plugin.environment.reason || 'Install the environment offered on the plugin’s card, then wait for its check to finish.',
    action('Prepare tools in My plugins', installedPath)))
  return rows
}

/** All readiness comes from the live probes. Clicks never mark a step ready. */
export function deriveJourney(value, { caps = {}, runtime = null, installed = [], catalog = null,
  productRows = [], interfaceProblem = '' } = {}) {
  const journey = normalizeJourney(value)
  if (!journey) return null
  const goal = SETUP_GOALS.find(item => item.id === journey.goal)
  const result = { title: goal.title, rows: [], ready: false, first: null }
  const tools = step => journeyToolPath(step, journey)
  if (journey.goal === 'dataset') {
    result.rows = [row('workspace', 'Start with your own images', true,
      'Import, organize, crop, caption by hand and export. No plugin or AI model is required.')]
    result.first = finish('Create your first dataset', 'Give it a name, import a few images, then try organizing and editing their captions.',
      '/datasets', 'Open LDS → Create a dataset')
  } else if (journey.goal === 'captions') {
    const llm = deriveSetupSteps(caps, runtime).find(step => step.id === 'ollama')
    const name = llm.isLmStudio ? 'LM Studio' : 'Ollama'
    result.rows = [
      row('service', 'Connect ' + name, llm.reachable,
        llm.reachable ? name + ' is responding.'
          : llm.managedInitializing ? 'The local AI service is starting. Wait for it, then check again.'
            : name + ' runs the AI that reads your images. Open its setup to install, start or connect it.',
        action('Set up ' + name, tools('ollama'))),
      row('model', 'Prepare a vision model', llm.reachable && llm.visionModelReady,
        llm.visionModelReady ? 'The configured vision model is available.'
          : 'The service needs a model that can read images. Open setup to select or download it; the model and hardware guidance are shown there.',
        action(llm.isLmStudio ? 'Load a vision model' : 'Choose and download a vision model', tools('ollama'))),
    ]
    result.first = finish('Caption a few images', 'Create or open a dataset, import images, then open Captions and choose your local captioner.',
      '/datasets?section=captions', 'Open datasets → Captions')
  } else if (journey.goal === 'images') {
    const engine = engineCatalog().find(item => item.id === journey.engine)
    if (!engine) return { ...result, chooseEngine: true }
    result.title = 'Generate images with ' + engine.label
    if (engine.plugin) {
      const plugin = installed.find(item => item.id === engine.plugin)
      result.rows.push(...pluginLifecycle(plugin, null, { ...journey, plugin: engine.plugin }))
    }
    if (engine.kind === 'local') result.rows.push(row('service', 'Connect ComfyUI', caps.comfyui?.reachable === true,
      caps.comfyui?.reachable ? 'ComfyUI is responding. The chosen model is checked next.'
        : 'ComfyUI runs image generation on your GPU. Setup explains how to install it or connect an existing installation.',
      action('Set up ComfyUI', tools('comfyui'))))
    const target = engine.plugin ? pluginSettingsPath(engine.plugin)
      : tools(engine.id === 'krea' ? 'install' : 'comfyui')
    result.rows.push(row('engine', 'Prepare ' + engine.label, caps.engines?.[engine.id] === true,
      caps.engines?.[engine.id] ? 'The app’s readiness check reports this engine as available.'
        : engine.kind === 'local' ? 'Prepare this engine’s model files and required components. The installer shows the files, sizes and any missing tools before you start.'
          : 'Open the plugin settings to connect your account or API key, then save and test the connection. Check the provider’s pricing before generating.',
      action(engine.kind === 'local' ? 'Prepare ' + engine.label : 'Connect ' + engine.label, target)))
    result.first = finish('Generate your first image', 'Create or open a character dataset and add a reference photo. In Add images → Generate variations, choose ' + engine.label + ' and enter your prompt.',
      '/datasets?section=add&panel=generate', 'Open datasets → Generate variations')
  } else {
    const product = journeyProducts(catalog, installed).find(item => item.id === journey.plugin)
    if (!journey.plugin) return { ...result, choosePlugin: true }
    const plugin = installed.find(item => item.id === journey.plugin)
    result.title = 'Get started with ' + (product?.name || plugin?.name || journey.plugin)
    result.rows = pluginLifecycle(plugin, product, journey)
    if (result.rows.every(item => item.ready)) {
      if (interfaceProblem) result.rows.push(row('interface', 'Load the plugin interface', false,
        interfaceProblem, { label: 'Reload LDS', kind: 'reload' }))
      else if (productRows.length && !productRows.some(item => item.label === journey.capability)) {
        return { ...result, chooseCapability: true }
      } else if (productRows.length) {
        const selected = productRows.find(item => item.label === journey.capability)
        const destination = capabilityDestination({ ...selected, ok: selected.state === 'ready', pending: selected.state === 'pending' })
        let target = localJourneyPath(destination?.href) || pluginSettingsPath(plugin.id) + '?focus=plugin-preparation'
        if (target.startsWith('/setup')) {
          const query = new URL(target, 'http://lds.invalid').searchParams
          target = journeyToolPath(query.get('step') || 'tools', journey)
        }
        result.rows.push(row('function', selected.label, selected.state === 'ready',
          selected.note || selected.what || 'Open the plugin’s preparation page to check and prepare this function.',
          action('Prepare this function', target)))
      } else {
        result.manual = true
        result.rows.push(row('manual', 'Check the plugin’s setup instructions', false,
          product?.experience?.setup_hint || 'This plugin does not publish an automatic readiness check. Open its settings and follow its instructions before your first try.',
          action('Open plugin settings', pluginSettingsPath(plugin.id))))
      }
    } else result.rows.push(row('function', 'Prepare the function you want to use', false,
      'After activation, choose a function. Its own checks will tell you which models or services are needed.',
      action('Open My plugins', '/plugins?tab=installed')))
    result.first = { title: 'Try your plugin', description: journey.capability
      ? 'Open the plugin and try ' + journey.capability + '. Other optional functions can be prepared later.'
      : 'Use the plugin’s own entry points to start your first task.',
    links: (product?.experience?.entrypoints || []).filter(item => localJourneyPath(item.path))
      .map(item => action(item.label, item.path)) }
  }
  result.next = result.rows.find(item => !item.ready)
  result.ready = result.rows.length > 0 && !result.next
  return result
}
