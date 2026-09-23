// Markdown ships with this product version. Lines stay editable without a Markdown loader.
export const GUIDE = {
  chapters: [],
  sections: [
{"chapter": "settings-reference", "anchor": "api-image-engines-configuration-keys", "markdown": [
        "## API image engines configuration keys",
        "",
        "These advanced values belong to this plugin. Change them only when its normal controls do not cover your need.",
        "| Key | Default | Notes |",
        "|---|---|---|",
        "| `engines.chatgpt_subscription_model` | `gpt-5.4-mini` | The Codex **router** model used by the subscription lane — not the image model. The subscription lane renders on whatever image model your plan serves; the API-key lane's image model is `engines.chatgpt_image_model`. |",
        "",
        "| Key | Meaning |",
        "|---|---|",
        "| `engines.chatgpt_auth` | Which credential the ChatGPT engine uses: `auto` (subscription when connected, else API key), `api`, or `subscription`. |",
        "| `engines.openrouter_model` | Image model slug the OpenRouter engine requests. Free text; blank = `google/gemini-3-pro-image`. Must accept reference images. |",
        "| `engines.nanobanana_model` | Image model the Nano Banana engine requests. Free text; blank = the `NANOBANANA_MODEL` environment variable if set, else `gemini-3-pro-image`. Must accept reference images. |",
        "| `engines.chatgpt_image_model` | Image model the ChatGPT engine requests on the **API-key** lane. Free text; blank = the `CHATGPT_IMAGE_MODEL` environment variable if set, else `gpt-image-2.5-sunburst`, the plugin default. Must accept reference images. The subscription lane ignores it. |",
        "| `engines.chatgpt_subscription_model` | Codex **router** model for the subscription lane (default `gpt-5.4-mini`) — not an image model. |",
      ].join("\n") + "\n"},
    {
      chapter: "settings-reference",
      anchor: "api-keys",
      markdown: [
        "## API keys",
        "",
        "- **Gemini API key** — powers the Nano Banana engine. Paste it here and hit **Test** to confirm a key is saved; no provider request is made. Get one from [aistudio.google.com](https://aistudio.google.com) → *Get API key*.",
        "- **OpenAI API key** — powers the ChatGPT engine (`gpt-image-2.5-sunburst` by default). **Test** checks the saved key or connected subscription; it does not verify provider access. This key is **optional if you connect a ChatGPT subscription** below — the subscription lane can run the ChatGPT engine on your plan's image quota instead.",
        "- **OpenRouter API key** — powers the OpenRouter engine. Get one from [openrouter.ai/keys](https://openrouter.ai/keys). One account and one balance in front of most providers, *including the same models the two engines above call directly* — so it is the way in if you would rather not open an account per provider. **Test** only checks that a key is saved: OpenRouter bills per request, so the app never spends a credit just to light up a checkmark.",
        "",
        "All three are write-only secrets: blank once saved, replaced by typing a new value, cleared only via **Remove**.",
      ].join("\n") + "\n",
    },
    {
      chapter: "settings-reference",
      anchor: "image-models",
      markdown: [
        "## Image models",
        "",
        "One field per API engine — you choose the model each one asks for:",
        "",
        "- **Nano Banana (Gemini) model** → `engines.nanobanana_model`. Blank = **`gemini-3-pro-image`**, the model this engine has always used. Note that **no model choice changes Google's output filter** — see *What the Gemini engine will and will not do* below.",
        "- **ChatGPT (OpenAI) image model** → `engines.chatgpt_image_model`. Blank uses `CHATGPT_IMAGE_MODEL` if set, otherwise **`gpt-image-2.5-sunburst`**, the plugin default. Choose `gpt-image-2.5-flare` for faster generation or `gpt-image-2` to keep the previous model. Existing model choices are preserved. This setting applies only to API-key generation; the subscription uses the image model selected by your plan.",
        "- **OpenRouter model slug** → `engines.openrouter_model`. Blank = **`google/gemini-3-pro-image`** — the same weights the Nano Banana engine calls, so switching engine changes who bills you, not what the pictures look like.",
        "",
        "All three are **free text on purpose**: providers publish image models far faster than this app publishes releases, and a dropdown frozen into a build would be out of date the day it shipped and would lock you out of a model that works. A blank field follows the environment override or the plugin's current default. Type a model to keep that choice across updates. Generation costs depend on the selected model, quality, size and reference images; the app's estimates are approximate.",
      ].join("\n") + "\n",
    },
    {
      chapter: "settings-reference",
      anchor: "what-the-gemini-engine-will-and-will-not-do",
      markdown: [
        "## What the Gemini engine will and will not do",
        "",
        "Two properties of Nano Banana that no setting on this page can change. They are here because both are easier to meet in advance than to diagnose afterwards.",
        "",
        "**Google screens the image, and that screen has no switch.** Gemini checks the picture it has just produced. When that check trips, the API answers **HTTP 200 with no image** — a success envelope with nothing in it. LDS reports each one as a refusal on the tile, relays Google's own reason code (`IMAGE_SAFETY`, `PROHIBITED_CONTENT`…) when it gives one, and tells you at the end of a run how many were refused as opposed to how many genuinely failed. What it cannot do is stop them:",
        "",
        "- the four adjustable safety categories in the Gemini API act on the **prompt**. Nothing — no threshold, no `BLOCK_NONE`, no `OFF` — turns off the screen applied to the **returned image**, and Google does not document it. There is no setting for LDS to offer;",
        "- it has **many false positives**: everyday requests get refused, and the trip point is not something you can reason about from your prompt text;",
        "- it is **not deterministic**: the same prompt can pass on one attempt and be refused on the next. This is why neither the app nor this page tells you to retry or reword — that would be selling a coin toss as a remedy.",
        "",
        "A refusal never stops a batch: the remaining rows still get their attempt, and the count at the end is exact.",
        "",
        "**Adult content is not allowed on this engine.** Google's usage policy forbids it, with consequences up to restriction of your Google account. LDS is fail-closed on this: NSFW variations are never sent to an API engine — they exist only on the local **Klein** path. Nothing here is a way around the filter; it is a statement of which engine does what.",
        "",
        "**Every Gemini output carries SynthID.** Google applies its invisible provenance watermark to 100% of the images this engine returns. If your dataset is destined for training, that is a material property of your data and you should know it is there. What effect it has on trained LoRA weights is **unmeasured** — nobody has established that it degrades a LoRA, and nobody has established that it does not. LDS states its presence and makes no claim beyond that. Images from **Klein** and **Krea 2 Edit** (local ComfyUI) carry no SynthID.",
        "",
        "**Where the value comes from**, in order:",
        "",
        "1. what you type in this field;",
        "2. the `NANOBANANA_MODEL` / `CHATGPT_IMAGE_MODEL` environment variable, if you had set one (these existed before the fields did — your choice is still honoured, and is only overridden when you actually type a slug here);",
        "3. the built-in default above.",
        "",
        "A model typed here applies to the **next generation** — no restart.",
        "",
        "The model **must accept reference images** — the dataset generator always sends your reference photo(s) with the prompt, so a text-to-image-only model is not usable here. When a provider refuses one, the failed tile names the model and repeats the provider's own reason (unknown model, model that will not take image input, key rejected, organization not verified), and the run **stops** instead of asking the same refused question once per image. What no app can catch for you is a model that *accepts* the references and then ignores them: if generated faces stop resembling your subject right after a model change, change it back.",
        "",
        "Two provider-specific traps:",
        "",
        "- **OpenAI HTTP 403:** read the provider's error, check your key's project permissions and the requested model's access requirements. The status alone does not establish that the key is valid or that organization verification is the cause. Review the model and key in **Plugins → API image engines → Settings**.",
        "- The ChatGPT **subscription** lane ignores this field: it renders through OpenAI's own image tool on whatever model your plan serves. `engines.chatgpt_subscription_model` is a different setting again — the Codex *router* model of that lane, which decides nothing about the pixels.",
        "",
        "How many references a model takes varies (roughly 1 to 16 depending on the provider); the app sends every reference you gave it and, if the model refuses the request, says so and mentions the count rather than quietly dropping references you expected to be used.",
        "",
        "What OpenRouter does **not** change:",
        "",
        "- **Not cheaper by itself.** You still pay per image, at that model's rate, out of your OpenRouter credits.",
        "- **Not less restricted.** OpenRouter forwards to the same upstream providers, so the same content policies apply. NSFW variations still run on a local engine only.",
        "- **No subscription lane.** OpenRouter is credit-based; there is no equivalent of the ChatGPT-plan option below.",
        "",
        "When a generation fails, the tile names the cause in OpenRouter's own words — no key saved, key rejected, out of credits, unknown model, rate-limited. The four causes that would fail every remaining image identically (no key, rejected key, no credits, unknown model) **stop the rest of the batch** instead of asking the same refused question once per image. The app never falls back to another engine behind your back: if you picked OpenRouter, only OpenRouter is billed. A moderation block arrives *inside* a successful response rather than as an error code, so it is read out of the body and shown with the reasons the provider gave — a refused image costs that row, not the run.",
      ].join("\n") + "\n",
    },
    {
      chapter: "settings-reference",
      anchor: "chatgpt-subscription-experimental",
      markdown: [
        "## ChatGPT subscription (experimental)",
        "",
        "If you have a ChatGPT Plus/Pro plan, you can run the ChatGPT engine on your subscription's image quota instead of a pay-per-use API key. This uses the same sign-in lane as OpenAI's Codex CLI — it is **not a documented API and may stop working at any time**; you connect your own account at your own risk.",
        "",
        "- **Connect with ChatGPT** — starts an OAuth device-code sign-in; the badge then shows the connected account's email.",
        "- **Import from Codex CLI** — appears only if the app detects an existing `codex login` on this machine, and reuses that session.",
        "- **Disconnect** — signs out of the subscription lane.",
        "- **ChatGPT engine auth** → `engines.chatgpt_auth`. Chooses which credential the ChatGPT engine uses. Default **`auto`**.",
        "",
        "| Value | Behaviour |",
        "|---|---|",
        "| `auto` *(default)* | Use the subscription when connected, otherwise fall back to the API key. |",
        "| `api` | API key only — ignore the subscription. |",
        "| `subscription` | Subscription only — never touch the API key. |",
        "",
        "Good to know: in subscription mode you get up to **5 reference images** per generation (versus 16 on the API), your plan's image cap applies, and when the quota runs out mid-batch the remaining rows fail with a clear message — **the app never silently switches to your paid API key**.",
        "",
        "**When a generation fails on this lane**, the tile names the cause rather than showing a blank \"empty response\": a network drop or timeout, an OpenAI outage, a plan quota, a connection that needs reconnecting, a refusal by OpenAI's safety system — and, because this lane is undocumented, the case that matters most for it: *OpenAI is no longer serving image generation on this ChatGPT subscription*. That last one stops the run and points at API-key mode, which is the only way back. No message suggests retrying: whether the same call would pass a second time is exactly what the app cannot know. If OpenAI answers without an image **and** without a reason, the tile says so instead of picking a cause.",
      ].join("\n") + "\n",
    },
    {
      chapter: "using-the-app",
      anchor: "generate-dataset-images-with-api-image-engines",
      markdown: [
        "## Generate dataset images with API image engines",
        "",
        "Enable API image engines, then connect a provider in **Plugins → API image engines → Settings**. Choose Nano Banana, ChatGPT or OpenRouter in the dataset's generation controls.",
        "Each provider has its own authentication and model settings. A connected ChatGPT subscription can use its plan quota; API-key requests follow the provider's billing.",
        "The app shows the selected engine and estimated cost before generation. No other LDS product is required; Camera and Video may reuse the generated images later.",
      ].join("\n") + "\n",
    },
  ],
}

const HELP_SECTIONS = {
  "engines.chatgpt_auth": [
    "settings-reference",
    "chatgpt-subscription-experimental"
  ],
  "nanobanana-filter-and-synthid": [
    "settings-reference",
    "what-the-gemini-engine-will-and-will-not-do"
  ],
  "GEMINI_API_KEY": [
    "settings-reference",
    "api-keys"
  ],
  "OPENAI_API_KEY": [
    "settings-reference",
    "api-keys"
  ],
  "OPENROUTER_API_KEY": [
    "settings-reference",
    "api-keys"
  ],
  "engines.openrouter_model": [
    "settings-reference",
    "image-models"
  ],
  "engines.nanobanana_model": [
    "settings-reference",
    "image-models"
  ],
  "engines.chatgpt_image_model": [
    "settings-reference",
    "image-models"
  ]
}
export function guideHelp(topic) {
  if (topic.app?.route?.startsWith('/settings/') || topic.app?.route?.startsWith('/setup')) {
    const { route, ...app } = topic.app
    topic = { ...topic, app: { ...app, route: '/plugins/api_engines/settings',
      ...(route.startsWith('/settings/') ? { legacyRoute: route } : {}) } }
  }
  const target = HELP_SECTIONS[topic.id]
  return { ...topic, ...(target ? { guide: { chapter: target[0], anchor: target[1] } } : {}) }
}
