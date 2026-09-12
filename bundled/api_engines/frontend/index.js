import { MIGRATED_NEWS } from './migratedNews.js'
import { GUIDE, guideHelp } from './guide.js'
// API image engines — the frontend descriptor of the bundled `api_engines`
// plugin. Plain JS on purpose: node --test imports it (the parity, help and
// engine-catalog contracts), Vite globs it at build time (src/plugins/bundled.js).
// The React panels are lazy imports, so each is its own chunk and only loads
// where a surface mounts it.
//
// What it contributes:
//   - `engine.spec` — the three engines' catalog entries (lib/engineSpecs.js):
//     the core's src/engines/catalog.js merges them in at each read, so the
//     generate panel's cards, the Settings dropdown, the Setup rows and key
//     fields, the activity lanes and the cost estimate all know them — and
//     none of them does when the plugin is off.
//   - `settings.group` — the API image engines product settings,
//     right after the core's "Engines" group: the three API keys, the model
//     each engine asks for, and the ChatGPT subscription lane.
//   - help topics for those fields (the core's Settings search finds them, the
//     ? badges resolve) and the Nano Banana filter/SynthID note.
// No `lucide-react` import here: node resolves a bare package from the
// importing file's folder, and bundled/ has no node_modules — the tests that
// load this descriptor would die on it. The group's icon is the core's default.
import { setting } from '@lds/plugin-sdk/help'
import { API_ENGINE_SPECS } from './lib/engineSpecs.js'

export default {
  guide: GUIDE,
  id: 'api_engines',
  nav: [],
  routes: [],
  slots: {
    'engine.spec': API_ENGINE_SPECS,
    'settings.group': [
      { id: 'api-engines', section: 'engines', after: 'engines-keys',
        title: 'API engines — keys & models',
        blurb: 'Gemini, OpenAI and OpenRouter keys, the model each engine asks for, and the ChatGPT subscription lane.',
        // The words the Settings sidebar search matches the section on, in
        // addition to the core's own.
        keywords: ['gemini', 'openai', 'openrouter', 'api key', 'chatgpt', 'nano banana', 'subscription', 'gpt-image'],
        panel: () => import('./panels/ApiEnginesSettingsGroup.jsx') },
    ],
  },
  hosts: [],
  help: ([
    setting('engines.chatgpt_auth', 'engines', 'chatgpt-auth-mode', 'ChatGPT engine auth',
      ['chatgpt', 'auth', 'subscription', 'api key', 'codex', 'oauth', 'openai']),
    setting('GEMINI_API_KEY', 'engines', 'GEMINI_API_KEY', 'Gemini API key',
      ['gemini', 'api key', 'nano banana', 'nanobanana', 'google', 'key']),
    setting('OPENAI_API_KEY', 'engines', 'OPENAI_API_KEY', 'OpenAI API key',
      ['openai', 'api key', 'chatgpt', 'gpt-image', 'gpt', 'key']),
    setting('OPENROUTER_API_KEY', 'engines', 'OPENROUTER_API_KEY', 'OpenRouter API key',
      ['openrouter', 'open router', 'api key', 'key', 'credits', 'one key', 'no subscription',
        'gemini', 'gpt-image', 'seedream', 'flux']),
    setting('engines.openrouter_model', 'engines', 'engines-openrouter_model', 'OpenRouter model',
      ['openrouter', 'model', 'slug', 'model slug', 'gemini-3-pro-image', 'gpt-image-2', 'seedream',
        'flux', 'reference images', 'image model']),
    setting('engines.nanobanana_model', 'engines', 'engines-nanobanana_model', 'Nano Banana (Gemini) model',
      ['nano banana', 'nanobanana', 'gemini', 'model', 'image model', 'gemini-3-pro-image',
        'change model', 'choose model', 'reference images', 'NANOBANANA_MODEL']),
    setting('engines.chatgpt_image_model', 'engines', 'engines-chatgpt_image_model', 'ChatGPT (OpenAI) image model',
      ['chatgpt', 'openai', 'gpt-image', 'gpt-image-2', 'gpt-image-1.5', 'model', 'image model',
        'change model', 'choose model', '403', 'organization verification', 'verified',
        'reference images', 'CHATGPT_IMAGE_MODEL']),
    // Two properties of the Gemini engine that change what you get, and that no
    // amount of settings can change back. Its own topic rather than a line
    // under the engine-mode one: this answers "why did I get fewer images than
    // I asked for", a question people arrive at already frustrated.
    { id: 'nanobanana-filter-and-synthid', kind: 'section',
      title: 'Nano Banana: the output filter, and SynthID',
      keywords: ['nano banana', 'nanobanana', 'gemini', 'google', 'refused', 'refusal',
        'blocked', 'content filter', 'safety', 'imagesafety', 'empty response',
        'missing images', 'fewer images', 'synthid', 'watermark', 'provenance',
        'nsfw', 'policy', 'bikini', 'lingerie'],
      guide: { chapter: 'settings-reference', anchor: 'image-engines' },
      app: { route: '/datasets?section=add' } },
  ]).map(guideHelp),
  whatsNew: MIGRATED_NEWS,
  paritySkip: [],
}
