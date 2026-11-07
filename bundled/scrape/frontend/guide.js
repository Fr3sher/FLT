// Markdown ships with this product version. Lines stay editable without a Markdown loader.
export const GUIDE = {
  chapters: [],
  sections: [
{"chapter": "settings-reference", "anchor": "web-scraping-source-credentials", "markdown": [
        "## Web scraping source credentials",
        "",
        "- **Reddit client ID** → `REDDIT_CLIENT_ID` (secret). Optional. Reddit scans work out of the box using a shared public client ID, but that ID is rate-limited across everyone who uses it, so you can hit *\"rate limiting requests, retry in Ns\"* (429) before your first scan of the day. Your own free ID gives you a private quota and clears those. **Trap:** on reddit.com/prefs/apps, create the app as type **installed app** — a *web app* or *script* comes with a client secret, and Reddit then rejects the anonymous login this app uses (every scan fails with **401**). The field has a built-in step-by-step guide.",
        "",
        "- **Pexels API key (required for Pexels)** → `PEXELS_API_KEY` (secret). **Required** for any Pexels search — there's no shared fallback. The free quota is **200 requests/hour and 20,000/month**. [Create one here](https://www.pexels.com/api/key/). Note the standing warning: an API key alone does **not** authorize dataset or machine-learning use — configure this only if Pexels has explicitly authorized your use case.",
      ].join("\n") + "\n"},
    {
      chapter: "settings-reference",
      anchor: "klein-rescue-small-scraped-images",
      markdown: [
        "## Klein rescue — small scraped images",
        "",
        "- **Small-image rescue instruction** → `klein.small_image_prompt`. An optional free-text instruction for **one flow only**: the automatic Klein **rescue** of scraped images under 768 px. Default **empty** — and empty is intentional: with nothing here the app improves from the reference image alone rather than inventing a restoration prompt on your behalf. Unlike the identity prompts above, this field has **no built-in text behind it**, so it stays a plain empty box: there is nothing to pre-fill or reset to. Add an instruction only if you want to steer that rescue (e.g. \"sharpen skin texture, keep natural tones\"). The manual **\"Klein upscale & improve\"** action in the lightbox does **not** use this field — it has its own editable prompt under Plugins ▸ Klein Improve ▸ Settings (`identity_prompts.klein_improve`), which can also be turned off for a pure upscale.",
      ].join("\n") + "\n",
    },
    {
      chapter: "using-the-app",
      anchor: "import-images-with-web-scraping",
      markdown: [
        "## Import images with Web scraping",
        "",
        "Open **Add images** in a dataset or open an image bank. Choose **Scrape the web**, search by keyword or paste a gallery URL, scan, then select the images to import.",
        "Plugins ▸ Web scraping ▸ Settings checks the optional scraping dependencies. Some sources require your own API key or login session; source availability is reported by the scan.",
        "Imported images are copied into the chosen destination. Pexels credits and web-search source pages retain the attribution already supported by LDS. Review the destination before importing and curate the results afterward.",
        "When Video is also installed, Video Bank offers the same source picker for clips. Video is not required for image scraping.",
      ].join("\n") + "\n",
    },
  ],
}

const HELP_SECTIONS = {
  "REDDIT_CLIENT_ID": [
    "settings-reference",
    "web-scraping-source-credentials"
  ],
  "PEXELS_API_KEY": [
    "settings-reference",
    "web-scraping-source-credentials"
  ],
  "klein.small_image_prompt": [
    "settings-reference",
    "klein-rescue-small-scraped-images"
  ],
  "video-bank-scrape": [
    "using-the-app",
    "import-images-with-web-scraping"
  ],
  "workspace-scrape": [
    "using-the-app",
    "import-images-with-web-scraping"
  ],
  "bank-scrape": [
    "using-the-app",
    "import-images-with-web-scraping"
  ],
  "action-scrape-scan": [
    "using-the-app",
    "import-images-with-web-scraping"
  ],
  "action-scrape-websearch": [
    "using-the-app",
    "import-images-with-web-scraping"
  ]
}
export function guideHelp(topic) {
  if (topic.app?.route?.startsWith('/settings/') || topic.app?.route?.startsWith('/setup')) {
    const { route, ...app } = topic.app
    topic = { ...topic, app: { ...app, route: '/plugins/scrape/settings',
      ...(route.startsWith('/settings/') ? { legacyRoute: route } : {}) } }
  }
  const target = HELP_SECTIONS[topic.id]
  return { ...topic, ...(target ? { guide: { chapter: target[0], anchor: target[1] } } : {}),
    ...(["video-bank-scrape"].includes(topic.id) ? { requires: ['video'] } : {}) }
}
