// Historical IDs and dates are preserved when ownership moves out of the core feed.
export const MIGRATED_NEWS = [
{
    id: '2026-08-09-setup-chatgpt-subscription',
    date: '2026-08-09',
    title: 'Set up ChatGPT with your Plus/Pro plan, no API key',
    blurb:
      'The first-run Setup screen only ever offered an OpenAI API key, so the ChatGPT engine looked like it cost money per image. It now shows both ways in side by side — paste a key, or sign in once with your ChatGPT Plus/Pro subscription and run on your plan\'s image quota. The step turns green as soon as either one is in place.',
  },
{
    id: '2026-07-29-chatgpt-failures-name-their-cause',
    date: '2026-07-29',
    title: 'A failed ChatGPT generation now says what went wrong',
    blurb:
      'On a ChatGPT subscription, a dropped connection, a timeout, an OpenAI outage and a lane OpenAI had closed all came back as the same blank tile worded as if the provider had simply produced nothing. Each now names itself, and the two that stop a run say so: a refused connection asks you to reconnect, and an endpoint OpenAI no longer serves tells you to switch to API-key mode instead of leaving you searching your own settings. On the API key, a safety refusal is now told apart from a reference photo OpenAI could not read — opposite problems that used to share one sentence. OpenRouter does the same with the moderation reasons it returns inside a successful response. Where the cause genuinely cannot be read, the tile still says so rather than guessing.',
  },
{
    id: '2026-07-28-nano-banana-says-when-google-refused',
    date: '2026-07-28',
    title: 'Missing images from Nano Banana now say who refused them',
    blurb:
      'Google screens every image Gemini returns, and when it blocks one the API answers "success" with nothing in it. LDS used to call that an empty response and suggest retrying — so a refused request looked like a broken app. Each refused tile now names the cause and relays Google\'s own reason code, a run tells you how many were refused versus how many actually failed, and real problems (key, quota, connection) keep their own separate message. A batch never stops on a refusal. No promises attached: that filter is not configurable, it refuses ordinary requests, and the same prompt can pass one time and not the next.',
  },
{
    id: '2026-07-26-edit-the-reference-with-openrouter',
    date: '2026-07-26',
    title: '✦ Edit your reference photo with OpenRouter too',
    blurb:
      "The ✦ Edit button on the reference card only offered ChatGPT and Nano Banana Pro, so if OpenRouter was the account you actually pay for, retouching your reference meant opening a second one. OpenRouter is now a third choice in the modal, using the model you set in Settings › Image engines — the same one your variations run on. Everything else is unchanged: your reference and any extra images you drop in are all sent along so the face stays the same person, you get the Before/After, and you Keep or Discard. If the model you configured does not accept reference images, the failure now says so in OpenRouter's own words instead of looking like a refused prompt.",
  },
{
    id: '2026-07-26-pick-the-model-of-every-api-engine',
    date: '2026-07-26',
    title: '🎛️ Pick the model for Nano Banana and ChatGPT too, not just OpenRouter',
    blurb:
      "OpenRouter let you type any model you liked, while Nano Banana and ChatGPT were stuck on whatever the release hardcoded — a newer, cheaper or better model meant waiting for an update. All three now have a plain text field, side by side in Settings › Image engines › Image models. Leave a field blank and nothing changes: that engine keeps the exact model it has always used. And when a model does not work out, the failed tile now says why in the provider's own words — unknown model, key refused, a model that will not take your reference photos — instead of the old catch-all about a content-policy refusal, and the run stops on the first one rather than paying for the same refusal once per image. Two things worth knowing before you type: every model here must accept reference images, because the generator always sends your reference photos with the prompt; for an OpenAI HTTP 403, read the provider's error and check the key's project permissions and the requested model's access requirements. The status alone does not establish that the key is valid or that organization verification is the cause.",
  },
{
    id: '2026-07-26-openrouter-image-engine',
    date: '2026-07-26',
    title: '🔀 OpenRouter is now an image engine — one key instead of one per provider',
    blurb:
      'Generating a dataset meant an account at Google AND at OpenAI, one key each. If you already pay for OpenRouter — a single balance in front of every provider — there was no way in at all. There is now: paste your OpenRouter key in Settings › Image engines, tick the OpenRouter card in the generator, and it renders alongside (or instead of) the others. It reaches the SAME upstream models, so this changes who bills you, not what the images look like: the default is google/gemini-3-pro-image, exactly the weights the Nano Banana engine calls. The model is a plain text field, so you can point it at gpt-image-2, Seedream, FLUX or anything else OpenRouter serves that accepts reference images, without waiting for an update. When something goes wrong it says which thing — no key, key refused, out of credits, unknown model — and a run that cannot possibly succeed stops instead of paying for the same refusal once per image. Nothing about the existing engines changed. Suggested by jqs (GitHub #13).',
  },
]
