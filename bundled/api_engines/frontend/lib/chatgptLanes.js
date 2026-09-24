// The ChatGPT engine has TWO independent doors, and Setup only ever showed one.
// A single "OpenAI API key — ○ Not set" row taught every Plus/Pro subscriber, on
// the first screen they see, that this engine is pay-per-use — while the
// subscription lane (Codex device-code OAuth) had been shipping for months on a
// Settings page they had no reason to open yet. Either door lights the engine up,
// so the step must show both and go green on either.
//
// `keySet` comes from the SECRETS PRESENCE payload, not from engines.chatgpt:
// the backend ORs the two lanes into that one boolean (probe_openai), so once a
// subscription is connected it can no longer answer "is a key also set". Two
// lanes need two signals. `ready` still defers to the backend's OR, with the
// locally-visible lanes as the fallback for a payload that predates it.
//
// Pure JS (moved here from the core's useSetupSteps.js with the plugin): the
// Setup lane panel renders it, node --test locks the wording.
export const CHATGPT_API_KEY_SECRET = 'OPENAI_API_KEY'

export function chatgptLanes(caps, secretsPresence) {
  const c = caps || {}
  const sub = c.chatgpt_subscription || {}
  const connected = !!sub.connected
  const keySet = !!(secretsPresence || {})[CHATGPT_API_KEY_SECRET]
  const engine = (c.engines || {}).chatgpt
  return {
    ready: typeof engine === 'boolean' ? (engine || keySet || connected) : (keySet || connected),
    keySet,
    connected,
    // Both doors open is not a conflict to warn about — it is the belt-and-braces
    // setup the `auto` auth mode was written for (subscription first, key as the
    // fallback the user explicitly paid for). Named so the wizard can say which
    // one is actually carrying the engine instead of showing two green ticks with
    // no explanation of which one runs.
    both: keySet && connected,
  }
}

/** The one sentence under the ChatGPT heading in Setup — what is powering the
 *  engine right now, or what is still needed. Pure so node --test locks the
 *  wording, which is the part that was misleading. */
export function chatgptLaneSummary(lanes) {
  const l = lanes || {}
  if (l.both) {
    return 'Both lanes are set up. The engine uses your subscription first and '
      + 'falls back to the API key — change that in Settings ▸ Image engines.'
  }
  if (l.connected) return 'Ready through your ChatGPT subscription. No API key needed.'
  if (l.keySet) return 'Ready through your OpenAI API key, billed per image.'
  return 'Set up either one — an API key, or your ChatGPT Plus/Pro subscription. '
    + 'One is enough.'
}
