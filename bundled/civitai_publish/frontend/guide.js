// Markdown ships with this product version. Lines stay editable without a Markdown loader.
export const GUIDE = {
  chapters: [],
  sections: [
    {
      chapter: "using-the-app",
      anchor: "publish-a-lora-and-its-images-to-civitai",
      markdown: [
        "## Publish a LoRA and its images to Civitai",
        "",
        "Two gestures, one key. Both need the **Civitai API key** from **Plugins → Publish to Civitai → Settings** — the same one the scraper and the 🌐 prompt browser use",
        "(a free account has one).",
        "",
        "**1. The checkpoint → a model page.** Open a checkpoint pill's popover (on the",
        "◉ LoRA Canvas or a run's graph) and press **📤 Civitai**:",
        "",
        "- **Create the page from this checkpoint** — the form arrives pre-filled from",
        "  the run: model name, version name, the base model as Civitai names it",
        "  (Z-Image Turbo/Base, Krea 2, SDXL 1.0, FLUX.1 D, FLUX.2 Klein 4B-base /",
        "  9B-base — the official Klein weights this app trains on, which Civitai files",
        "  apart from the distilled lineage — Anima), the trigger word, a description",
        "  with the training facts (steps, epochs, rank/alpha, dataset version and image",
        "  count), tags and the licence toggles. A run trained on a **custom base** (a",
        "  ComfyUI checkpoint picked in the dropdown) leaves the base model **empty**",
        "  where Civitai distinguishes lineages — SDXL (Pony, Illustrious, NoobAI…),",
        "  Z-Image, Klein — because the app cannot honestly name it; pick it before",
        "  uploading. Press **Upload as a draft** and the `.safetensors` goes up in the",
        "  background; the page is created as a **draft** so you give it a last look on",
        "  Civitai (cover images, final read) before pressing Publish there. Tick",
        "  **Publish the page right away** to skip that step.",
        "- **Mark an existing page** — the LoRA already has a page? Paste its address,",
        "  press **Look up**: the page's name and its versions appear, the one the",
        "  address points at (`?modelVersionId=`) preselected, the newest otherwise.",
        "  Pick which version this checkpoint is and press **Link this version**.",
        "  Nothing is uploaded; the checkpoint is simply remembered as that version,",
        "  which is all the next gesture needs. The same two tabs open from a",
        "  picture's 📤 dialog: the picture names the checkpoint it was made with (its",
        "  stamp and the deployed LoRA name it ran with), and the app resolves which",
        "  save that is — no file to pick. **Unlink** forgets the link (the page on",
        "  Civitai is untouched); linking again simply retargets it.",
        "",
        "A linked pill shows **On Civitai** in its popover; the dialog opens the page,",
        "relinks it, or forgets the link (the page itself is never touched).",
        "",
        "**2. An image → a post under that page.** In the image viewer (Gallery,",
        "Canvas, checkpoint galleries, Test Studio), press **📤 Civitai**: the picture",
        "is posted under the page its checkpoint is linked to, with its prompt (the",
        "trigger word included, as it was actually sent), negative prompt, seed,",
        "sampler, CFG, steps, size and the LoRA weight — as Civitai generation data,",
        "so the post files itself under the right model (Civitai shows it in the",
        "model's gallery once its own scan of the image is done). **Publish the post",
        "right away** is on by default; untick it to leave a draft post you finish on",
        "Civitai.",
        "",
        "A picture carries the checkpoint it was made with only when that save has a",
        "step in its name. Every picture generated with a run's **final** save (the",
        "step-less `lora_<trigger>.safetensors`) — and every picture of a run you",
        "removed from the graph — has no stamp: the dialog then offers a **picker over",
        "the dataset's linked checkpoints**, which is the ordinary path for those, not a",
        "fallback. A run that ends on a numbered save writes two files at its last step",
        "(the numbered one and the final); each is its own page or version, linked by",
        "file, and the popover of each pill says which.",
        "",
        "What never leaves your machine: every image goes out as a **fresh PNG with no",
        "embedded metadata** (no EXIF, no ComfyUI workflow — the generation data",
        "travels explicitly), every text is stripped of local paths, and the",
        "checkpoint's own safetensors metadata is scanned for a machine path before a",
        "byte is uploaded — a file that names your machine is refused, and the dialog",
        "says which field.",
        "",
        "Links open on **civitai.com** by default; **Plugins → Publish to Civitai → Settings** switches them to **civitai.red** (the same site and",
        "account behind a second domain — pick the one you are signed in on, because a",
        "draft page is private and the sign-in is per domain). Uploads run in the",
        "background: closing the dialog loses nothing.",
      ].join("\n") + "\n",
    },
    {
      chapter: "settings-reference",
      anchor: "civitai-publishing",
      markdown: [
        "## Civitai publishing",
        "",
        "- **Open Civitai links on** → `civitai.link_host`. `civitai.com` (default) or `civitai.red`. The publisher's API calls always go to civitai.com; this only decides which domain the links the app shows you open on. civitai.red is the same site and account behind a second domain, but the sign-in is per domain — a **draft** model page is private to its owner, so opened on the domain you are not signed in on, your own draft answers a 404. Pick the one you use. The shared `CIVITAI_API_KEY` can be edited on this plug-in’s settings page. It is also used by the core Civitai prompt browser and optional Web scraping plug-in; there is no second credential.",
      ].join("\n") + "\n",
    },
  ],
}

const HELP_SECTIONS = {
  "civitai.link_host": [
    "settings-reference",
    "civitai-publishing"
  ]
}
export function guideHelp(topic) {
  if (topic.app?.route?.startsWith('/settings/') || topic.app?.route?.startsWith('/setup')) {
    const { route, ...app } = topic.app
    topic = { ...topic, app: { ...app, route: '/plugins/civitai_publish/settings',
      ...(route.startsWith('/settings/') ? { legacyRoute: route } : {}) } }
  }
  const target = HELP_SECTIONS[topic.id]
  return { ...topic, ...(target ? { guide: { chapter: target[0], anchor: target[1] } } : {}) }
}
