import { INPUT_CLASS, Card, SecretField } from '@lds/plugin-sdk/ui'
import { ResetToDefault } from '@lds/plugin-sdk/ui'
import ChatgptSubscriptionConnect from './ChatgptSubscriptionConnect.jsx'

/* API image engines ▸ Settings ▸ "Keys & models": the group this
   plugin contributes (`settings.group` in the descriptor). Three cards, moved
   here from the core's EnginesSection with the engines they configure: the
   API keys, the model each engine asks for, and the ChatGPT subscription lane.
   The core's own group next to it keeps what is the core's — which engines
   are on and which one opens preselected — and reads the API engines from
   the catalog this plugin fills.

   Every `id="…"` and `key: '…'` below is spelled out literally on purpose:
   the help-registry contract test scans these files for the focus anchors of
   the topics the descriptor declares, and a template-built id would be
   invisible to it (and to anyone grepping for the anchor). */

// `key` is the secret's name AND the DOM id (SecretField renders id={f.key}).
// One row per engine, in the engine order; the plugin's engine specs name the
// same three secrets (engineSpecs.test.js holds the two lists together).
const ENGINE_SECRETS = [
  { key: 'GEMINI_API_KEY', label: 'Gemini API key', testTarget: 'gemini', help: 'Powers the Nano Banana engine.' },
  { key: 'OPENAI_API_KEY', label: 'OpenAI API key', testTarget: 'openai',
    help: 'Powers the ChatGPT engine (gpt-image-2 by default). Optional if you connect a ChatGPT subscription below.' },
  { key: 'OPENROUTER_API_KEY', label: 'OpenRouter API key', testTarget: 'openrouter',
    help: 'Powers the OpenRouter engine: one account and one balance in front of the same '
      + 'upstream image models, including the ones the two engines above call directly. '
      + 'Test only checks that a key is saved — OpenRouter bills per request, so nothing '
      + 'is sent until you generate.' },
]

/* One model field per API engine (feature request — the OpenRouter engine
   shipped with a free-text model while Nano Banana and ChatGPT were frozen to
   whatever the release hardcoded, overridable only by an environment variable
   nobody could see from the app).

   Free text on all three, deliberately: providers ship image models far faster
   than this app ships releases, so a dropdown baked into a build would be stale
   the day it landed and would lock people out of a model that works.

   Blank = the historical default, so a field appearing changes nobody's result.
   The resolution order is documented next to each backend engine:
   setting > environment variable > built-in default — a NANOBANANA_MODEL /
   CHATGPT_IMAGE_MODEL exported before these fields existed is still honoured and
   is only overridden when someone actually types a slug here.

   One card rather than three: the three fields answer the same question, and on
   a phone three cards of one input each is a lot of scrolling for very little. */
function ModelField({ id, configKey, label, placeholder, config, setField, configDefaults, children }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-content">{label}</label>
      <input
        id={id}
        type="text"
        spellCheck="false"
        autoComplete="off"
        autoCapitalize="off"
        value={config.engines[configKey] ?? ''}
        onChange={(e) => setField('engines', configKey, e.target.value)}
        placeholder={placeholder}
        className={INPUT_CLASS}
      />
      <p className="mt-1 text-xs text-content-muted">{children}</p>
      {/* Two of these three default to BLANK — "let the engine pick", which also
          keeps a pre-existing NANOBANANA_MODEL / CHATGPT_IMAGE_MODEL environment
          variable in charge. Reset writes the shipped default back, so on those
          two it empties the field instead of typing a slug in: it hands the
          implicit state back rather than pinning today's model forever. */}
      <ResetToDefault label={label} section="engines" field={configKey}
        config={config} configDefaults={configDefaults} setField={setField} />
    </div>
  )
}

function ImageModelsCard({ config, setField, configDefaults }) {
  const shared = { config, setField, configDefaults }
  return (
    <Card
      id="engine-image-models"
      title="Image models"
      help="Which model each API engine asks for. Free text on purpose: providers publish new image models far faster than this app publishes releases, and a fixed menu would be out of date the day it shipped. Leave a field blank to keep the model the engine has always used — an empty field changes nothing about your results. All three must accept REFERENCE IMAGES: the dataset generator always sends your reference photos with the prompt, so a text-to-image-only model cannot work here; when a provider refuses one, the failed tile names the model and the provider's own reason instead of blaming your prompt, and the run stops rather than paying for the same refusal once per image."
    >
      <ModelField {...shared} id="engines-nanobanana_model" configKey="nanobanana_model"
        label="Nano Banana (Gemini) model" placeholder="gemini-3-pro-image">
        Blank = <code className="break-all">gemini-3-pro-image</code>, the model this engine has
        always used. Any Gemini <strong>image</strong> model that accepts image input works —
        browse them at{' '}
        <a href="https://ai.google.dev/gemini-api/docs/models" target="_blank" rel="noreferrer"
          className="text-primary underline">ai.google.dev</a>.
      </ModelField>

      <ModelField {...shared} id="engines-chatgpt_image_model" configKey="chatgpt_image_model"
        label="ChatGPT (OpenAI) image model" placeholder="gpt-image-2">
        Blank uses <code className="break-all">CHATGPT_IMAGE_MODEL</code> if set, otherwise{' '}
        <code className="break-all">gpt-image-2</code>, this plugin's default.
        If a request returns HTTP 403, read the provider's error and check your key's
        project permissions and the requested model's access requirements.
        The status alone does not confirm that the key is valid or that organization
        verification is the cause.
        Applies to the API-key lane — the ChatGPT <em>subscription</em> lane renders on whatever
        image model your plan serves and ignores this field.
      </ModelField>

      <ModelField {...shared} id="engines-openrouter_model" configKey="openrouter_model"
        label="OpenRouter model slug" placeholder="google/gemini-3-pro-image">
        Blank = <code className="break-all">google/gemini-3-pro-image</code> — the same weights the
        Nano Banana engine calls, so switching engine changes who bills you, not the picture.
        Browse the list at{' '}
        <a href="https://openrouter.ai/models?output_modalities=image" target="_blank" rel="noreferrer"
          className="text-primary underline">openrouter.ai/models</a>.
      </ModelField>
      <p className="border-t border-border pt-3 text-xs text-content-subtle">
        A model must accept your reference photos. One that only takes text will either be
        refused — the tile then says which model and why — or quietly ignore the references and
        return a picture of someone else, which no app can detect for you. If generated faces stop
        looking like your subject after a model change, change it back.
      </p>
    </Card>
  )
}

const CHATGPT_AUTH_OPTIONS = [
  { id: 'auto', label: 'Auto — subscription when connected, otherwise API key' },
  { id: 'api', label: 'API key only' },
  { id: 'subscription', label: 'Subscription only' },
]

/* ChatGPT subscription (Codex OAuth) — EXPERIMENTAL lane. The device-code login
   itself is ChatgptSubscriptionConnect: the Setup wizard's image step offers
   the same connection (ChatgptSetupLane), and two copies of an OAuth polling
   loop would be two chances for them to drift. This card adds what only
   Settings has: the auth-mode preference. */
function ChatgptSubscriptionCard({ caps, config, setField, refreshCaps, toast, configDefaults }) {
  return (
    <Card
      title="ChatGPT subscription (experimental)"
      help="Run the ChatGPT engine on your ChatGPT Plus/Pro image quota instead of a pay-per-use API key. Undocumented lane — it may stop working if OpenAI closes it. Limits vs API mode: up to 5 reference images (instead of 16), your plan's daily image cap applies, SFW only."
    >
      <ChatgptSubscriptionConnect caps={caps} refreshCaps={refreshCaps} toast={toast} />

      <div>
        <label htmlFor="chatgpt-auth-mode" className="block text-sm font-medium text-content">ChatGPT engine auth</label>
        <select
          id="chatgpt-auth-mode"
          value={config.engines.chatgpt_auth || 'auto'}
          onChange={(e) => setField('engines', 'chatgpt_auth', e.target.value)}
          className={INPUT_CLASS}
        >
          {CHATGPT_AUTH_OPTIONS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
        <p className="mt-1 text-xs text-content-muted">
          When the subscription quota runs out mid-batch, remaining rows fail with a clear message — the app never silently switches to your paid API key.
        </p>
        <ResetToDefault label="ChatGPT engine auth" section="engines" field="chatgpt_auth"
          config={config} configDefaults={configDefaults} setField={setField} />
      </div>
    </Card>
  )
}

/** The group's body. Receives the whole EnginesSection prop bag — the same
 *  `config`/`setField`/secret helpers the core's cards use, so a key saved
 *  here and a key saved there go through one write path. */
export default function ApiEnginesSettingsGroup(props) {
  const { config, setField, caps, refreshCaps, toast, configDefaults } = props
  return (
    <>
      <Card title="API keys" help="Keys are write-only — fields stay blank even when a key is already saved.">
        {ENGINE_SECRETS.map((f) => <SecretField key={f.key} field={f} {...props} />)}
      </Card>

      <ImageModelsCard config={config} setField={setField} configDefaults={configDefaults} />

      <ChatgptSubscriptionCard caps={caps} config={config} setField={setField} refreshCaps={refreshCaps}
        toast={toast} configDefaults={configDefaults} />
    </>
  )
}
