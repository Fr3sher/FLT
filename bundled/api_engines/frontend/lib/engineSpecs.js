// The three API engines' catalog entries — what this plugin contributes to
// the core's `engine.spec` slot (frontend/src/engines/catalog.js merges them
// in at each read). Same facts as the backend half (lds_api_engines/__init__.py
// registers the same three through ctx.register_engine), plus what only a
// screen needs: the accent, the Settings and Setup wording, the card and the
// note panels, and — for ChatGPT — when its lane is free.
//
// The FIRST LINE of each entry keeps the exact shape
// `{ id: '…', label: '…', kind: 'api', order: N,` on purpose: two contract
// tests read this file as TEXT — frontend/tests/engine-catalog-contract.test.mjs
// (against the Python catalog) and backend/tests/test_engine_lists_contract.py.
//
// ⚠️ Engine ids never change: they are on disk (the filename tag), in the
// database (a row's engine) and in localStorage. Append, never rename.

/** The ChatGPT engine runs on the subscription lane — plan quota, not
 *  dollars — when the auth mode says so, or when it is `auto` and a
 *  subscription is connected. Mirrors the backend's "auto = subscription when
 *  connected". Pure, so the card and the cost estimate cannot disagree. */
export function chatgptViaSubscription({ caps, engineConfig } = {}) {
  const auth = (engineConfig || {}).chatgpt_auth || 'auto'
  const sub = (caps || {}).chatgpt_subscription || {}
  return auth === 'subscription' || (auth === 'auto' && !!sub.connected)
}

export const API_ENGINE_SPECS = [
  { id: 'nanobanana', label: 'Nano Banana Pro', kind: 'api', order: 2,
    rate: 0.15, remote: true, billable: true, secret: 'GEMINI_API_KEY', keyTestTarget: 'gemini',
    recommended: true, modelSettingKey: 'nanobanana_model',
    settingsLabel: 'Nano Banana (Gemini)', shortLabel: 'Nano Banana',
    setupRow: { label: 'Nano Banana (Gemini)',
      what: "Generates test images from a prompt — Google's cloud engine (API key)", topic: 'GEMINI_API_KEY' },
    // The Setup wizard's key field (the "Image generation" step).
    setupKey: { label: 'Gemini API key', href: 'https://aistudio.google.com/apikey',
      help: 'Powers Nano Banana.' },
    accent: {
      card: 'border-amber-400/60 bg-amber-500/15 ring-1 ring-amber-400/40',
      title: 'text-amber-200', text: 'text-amber-300', icon: 'text-amber-300',
      pill: 'bg-amber-500/25 text-amber-200', dot: 'bg-amber-400',
    },
    card: () => import('../panels/NanobananaCard.jsx'),
    // Two facts about the Gemini engine that belong next to the choice.
    note: () => import('../panels/NanobananaNote.jsx'),
  },
  { id: 'chatgpt', label: 'ChatGPT', kind: 'api', order: 3,
    rate: 0.17, remote: true, billable: true, secret: 'OPENAI_API_KEY', keyTestTarget: 'openai',
    recommended: true, modelSettingKey: 'chatgpt_image_model',
    settingsLabel: 'ChatGPT (OpenAI)', shortLabel: 'ChatGPT',
    setupRow: { label: 'ChatGPT (gpt-image-2)',
      what: "Generates test images — OpenAI's cloud engine (API key)", topic: 'engines.chatgpt_auth' },
    // NOT "Powers ChatGPT (gpt-image-2)". That sentence was true and still
    // misleading: it made the paid API key read as the only way in, on the
    // screen where a ChatGPT Plus/Pro subscriber decides what this app can do —
    // while the subscription lane sat two pages away in Settings. The key row
    // describes ITS lane; the engine's other door is the panel below.
    setupKey: { label: 'OpenAI API key', href: 'https://platform.openai.com/api-keys',
      help: 'Pay-per-image, and the lane that accepts up to 16 reference images.' },
    // Two doors into ONE engine: the panel wraps the key field with the
    // engine's own heading and the subscription lane under it.
    setupPanel: () => import('../panels/ChatgptSetupLane.jsx'),
    // The subscription lane spends plan quota, not dollars.
    freeWhen: chatgptViaSubscription,
    accent: {
      card: 'border-sky-400/60 bg-sky-500/15 ring-1 ring-sky-400/40',
      title: 'text-sky-200', text: 'text-sky-300', icon: 'text-sky-300',
      pill: 'bg-sky-500/25 text-sky-200', dot: 'bg-sky-400',
    },
    card: () => import('../panels/ChatgptCard.jsx'),
  },
  { id: 'openrouter', label: 'OpenRouter', kind: 'api', order: 4,
    rate: 0.15, remote: true, billable: true, secret: 'OPENROUTER_API_KEY', keyTestTarget: 'openrouter',
    recommended: true, modelSettingKey: 'openrouter_model',
    settingsLabel: 'OpenRouter', shortLabel: 'OpenRouter',
    setupRow: { label: 'OpenRouter',
      what: 'Generates test images through OpenRouter-hosted models (API key)', topic: 'OPENROUTER_API_KEY' },
    setupKey: { label: 'OpenRouter API key', href: 'https://openrouter.ai/keys',
      help: 'Powers the OpenRouter engine — one key and one balance for the same '
        + 'upstream models. Pick the model in Settings › Image engines.' },
    accent: {
      card: 'border-fuchsia-400/60 bg-fuchsia-500/15 ring-1 ring-fuchsia-400/40',
      title: 'text-fuchsia-200', text: 'text-fuchsia-300', icon: 'text-fuchsia-300',
      pill: 'bg-fuchsia-500/25 text-fuchsia-200', dot: 'bg-fuchsia-400',
    },
    card: () => import('../panels/OpenrouterCard.jsx'),
  },
]
