// Historical IDs and dates are preserved when ownership moves out of the core feed.
export const MIGRATED_NEWS = [
  {"id": "2026-09-23-web-video-selection", "date": "2026-09-23", "title": "Select all the web videos you need", "blurb": "Video imports no longer ask you to reduce your selection to six videos. Bank imports continue through the whole selection in successive batches.", "to": "/datasets"},
{
    id: '2026-09-23-scrape-video-dataset', date: '2026-09-23',
    title: 'Import web videos directly into a dataset',
    blurb: 'In a video dataset, open Add videos, scan a website URL and select the videos to import. The picker shows videos, and the import runs in the background with progress and skipped-file counts.',
    to: '/datasets',
},
{
    id: '2026-08-06-bank-scrape-keeps-provenance',
    date: '2026-08-06',
    title: 'Images scraped into a bank keep their source',
    blurb: 'Scraping straight into a bank used to drop the Pexels credit or the page a web-search image was found on. It now survives the trip — and shows up again if you later promote that image into a dataset.',
  },
{
    id: '2026-07-28-scrape-straight-into-a-bank',
    date: '2026-07-28',
    title: 'Scrape the web straight into a bank — no throwaway dataset first',
    blurb:
      'The scraper had one outlet: straight into a dataset, through filters made for training — anything under 768 px, anything wider than 3:1 and anything it judged a near-duplicate was dropped before you ever saw it. Getting a scrape into the Image bank meant building a dataset you did not want, then importing it back, having already lost the images the triage passes exist to judge. The Image bank page now has its own scrape section: same scan, same picking, you just choose which bank receives them — a new one, or more into a bank you are already triaging. Nothing is filtered on the way in; the quality, duplicate and framing passes rule on the pile, and you promote the keepers into a dataset as usual.',
  },
{
    id: '2026-07-22-install-everything-covers-scraper',
    date: '2026-07-22',
    title: '⬇ "Install everything" now repairs the scraper too',
    blurb:
      "The scraper packages were the one component Install everything never touched: it reported everything was already in place while a source kept failing on a missing package. They are now part of the plan, and the check looks at every package the scraper imports — so a package added by an update (instaloader, for Instagram) is picked up instead of staying invisible until you found the per-tile Reinstall button.",
  },
{
    id: '2026-07-21-instagram-scrape-and-english-messages',
    date: '2026-07-21',
    title: '📸 Instagram scraping is back — and every scraper speaks English',
    blurb:
      "Instagram scraping works again: the missing 'instaloader' dependency now ships with the scrape extras (Setup › Install everything). Every scraper error message — Instagram, Civitai, Pexels, Reddit, RedGifs, Picazor, Erome and more — now reads in clear English, and the \"missing dependency\" ones tell you exactly which extra to install.",
  },
{
    id: '2026-07-17-scrape-section',
    date: '2026-07-17',
    title: 'A dedicated 🕸 Scrape section',
    blurb:
      'Scanning a gallery is now its own step in every dataset. Paste a gallery URL, pick the images you want, and import them full-frame — then crop each one afterwards right on its tile.',
  },
]
