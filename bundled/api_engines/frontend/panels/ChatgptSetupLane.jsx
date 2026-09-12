import ChatgptSubscriptionConnect from './ChatgptSubscriptionConnect.jsx'
import { chatgptLanes, chatgptLaneSummary } from '../lib/chatgptLanes.js'

/* The ChatGPT engine on the Setup wizard's "Image generation" step — the
   panel the engine spec names as `setupPanel`, rendered by the core in the
   place of the plain key field.

   Two doors into ONE engine, so the ✓ belongs to the engine and each lane
   carries its own smaller state. Attaching "✓ Ready" to the API-key row — as
   the screen once did — meant a subscriber with no key at all watched the key
   field certify itself green, and a keyless user saw "○ Not set" on an engine
   that was already working.

   FLAT, like its neighbours: the engine gets the same heading line and the
   same right-hand state as "Gemini API key" or "OpenRouter API key", and its
   two lanes hang under it as ordinary rows. The nested bordered card this used
   to be described the same thing correctly and broke the rhythm of the page
   doing it — the one engine on the screen that looked like a different kind
   of object.

   `keyField({ ok, muted })` is the core's own key input for this engine (the
   same one every other API engine gets), rendered with the state THIS panel
   decides: the key lane's ✓ is "a key is saved", not "the engine is ready". */
export default function ChatgptSetupLane({ keyField, caps, refresh, toast, secretsPresence }) {
  const chatgpt = chatgptLanes(caps, secretsPresence)
  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-content">ChatGPT (gpt-image-2)</span>
          <span className={`text-xs ${chatgpt.ready ? 'text-emerald-400' : 'text-content-subtle'}`}>
            {chatgpt.ready ? '✓ Ready' : '○ Not set up'}
          </span>
        </div>
        <p className="text-xs text-content-muted">{chatgptLaneSummary(chatgpt)}</p>
      </div>
      {keyField({ ok: chatgpt.keySet, muted: true })}
      {/* The SAME component this product's settings mount — one device-code
          flow, so the two screens cannot disagree about what "connected"
          means. Given a label it renders as one sober row (state inline,
          compact button) instead of a badge adrift opposite a full-width call
          to action. */}
      <ChatgptSubscriptionConnect caps={caps} refreshCaps={refresh} toast={toast}
        label="ChatGPT Plus/Pro subscription"
        description={'Runs on your plan’s image quota instead of a paid key. '
          + 'Experimental and undocumented by OpenAI — up to 5 reference images, '
          + 'your plan’s daily cap applies, SFW only.'} />
    </div>
  )
}
