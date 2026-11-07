// Setup offers owned by web scraping. The installer keeps the shared environment machinery.
export const SCRAPE_ML_CARDS = [
  { action: 'scrape_extras', cap: 'scrape_deps', icon: '🔎',
    title: 'Scraping extras (gallery links & keyless web image search)',
    body: 'Installs curl_cffi, gallery-dl, cloudscraper, ddgs and yt-dlp — what gallery-URL scraping, the keyless web image search and the video sources use to enumerate and fetch media. Pexels enumeration works without it (its official API); fetching the actual images still needs curl_cffi. Without it, scraping is limited to sources with no anti-bot layer.' }
]

export const SCRAPE_QUALITY_UNLOCKS = ['Scraping extras (optional)']

export function scrapeSetupRows(caps) {
  return [{ label: 'Scraping extras (optional)', what: 'Gallery links, keyless web image search and video sources (gallery-dl, yt-dlp…)', ok: !!caps?.scrape_deps, topic: 'setup-quality' }]
}
