import { MIGRATED_NEWS } from './migratedNews.js'
import { GUIDE, guideHelp } from './guide.js'
// Web scraping — the frontend descriptor of the bundled `scrape` plugin.
// Plain JS on purpose: node --test imports it (the parity contract), Vite
// globs it at build time (src/plugins/bundled.js). The React panels are lazy
// imports, so they only load when a surface mounts them, and each panel is
// its own chunk.
//
// One contribution, three surfaces: the dataset workspace's 🕸 Scrape section,
// the image Bank list and the video Bank list all carry the same "scan a
// gallery, pick, import" panel — that is the Bank↔Dataset parity rule, and
// PAIRED_SURFACES['sources.panel'] is what checks it.
import { SCRAPE_TOPICS } from './help/scrapeTopics.js'
import { SCRAPE_ML_CARDS, SCRAPE_QUALITY_UNLOCKS, scrapeSetupRows } from './lib/scrapeSetup.js'

export default {
  guide: GUIDE,
  id: 'scrape',
  nav: [],
  routes: [],
  slots: {
    'settings.group': [{
      id: 'web-scraping', section: 'scraping', title: 'Web scraping',
      blurb: 'Source credentials and automatic rescue of small scraped images.',
      keywords: ['reddit', 'client id', 'pexels', 'pexels api', 'api key', 'quota', 'rate limit', '429',
        'scrape', 'scraper', 'klein', 'small image', 'rescue', 'upscale'],
      panel: () => import('./panels/ScrapeSettingsGroup.jsx'),
    }],
    'setup.step': [{ id: 'scrape', rows: scrapeSetupRows,
      mlCards: SCRAPE_ML_CARDS, qualityUnlocks: SCRAPE_QUALITY_UNLOCKS }],
    'sources.panel': [
      {
        id: 'scan',
        panels: {
          dataset: () => import('./panels/ConceptSourcesPanel.jsx'),
          bank: () => import('./panels/BankScrapePanel.jsx'),
          videoBank: () => import('./panels/VideoBankScrapePanel.jsx'),
          videoDataset: () => import('./panels/VideoDatasetScrapePanel.jsx'),
        },
      },
    ],
  },
  hosts: [],
  help: ([...SCRAPE_TOPICS]).map(guideHelp),
  whatsNew: MIGRATED_NEWS,
  paritySkip: [],
}
