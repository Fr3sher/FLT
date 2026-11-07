# Publish to Civitai

Publish a trained LoRA checkpoint as a Civitai model page, or link the page it
already has. Post generated images under that page with their generation data.
The plugin owns the publishing dialog, checkpoint and image actions, help and
settings. Canvas, Web scraping and HF Publish are optional integrations.

Configure the shared Civitai API key under Plugins → Publish to Civitai → Settings.
The key is also used by the core prompt browser and, when installed, Web scraping.
Changing it applies to those consumers too. The link-domain choice controls which
site opens in the browser; API requests always use civitai.com.

Checkpoint uploads default to a draft. Generated image posts default to immediate
publication; the dialog lets you choose a draft instead. Images are re-encoded
without embedded metadata, outgoing text is redacted, and checkpoint metadata is
checked for local paths before upload. The local link store retains the historical
`civitai_link` table identity. Unlinking forgets the local association; it does not
delete a page on Civitai.

Requires LDS API 1.12 or later in major version 1. No model or custom node download
is needed. The publishing service uses the host's shared training-history and
image-export interfaces; it does not import another plugin.
