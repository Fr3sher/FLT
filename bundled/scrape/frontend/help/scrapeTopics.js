/* The scraping feature's help travels with its panels and settings. */
import { action, setting } from '@lds/plugin-sdk/help';

export const SCRAPE_TOPICS = [
  action('action-scrape-scan', 'Scan a gallery URL',
    ['scrape', 'scan', 'gallery', 'url', 'import', 'concept'],
    '/datasets?section=scrape&panel=scan', 'using-the-app', 'concept-datasets-an-object-or-action-not-a-person'),
  action('action-scrape-websearch', 'Search the web for images by keyword',
    ['scrape', 'search', 'websearch', 'web images', 'keyword', 'duckduckgo', 'import', 'concept'],
    '/datasets?section=scrape&panel=scan', 'using-the-app', 'concept-datasets-an-object-or-action-not-a-person'),
  { id: 'workspace-scrape', kind: 'section', title: 'Scrape',
    keywords: ['scrape', 'scan', 'gallery', 'url', 'source', 'import', 'concept'],
    guide: { chapter: 'using-the-app', anchor: 'concept-datasets-an-object-or-action-not-a-person' },
    app: { route: '/datasets?section=scrape&panel=scan' },
    tip: { trigger: 'add-images-visit',
      text: 'Scraping now lives in its own Scrape section of the sidebar.' } },
  action('bank-scrape', 'Scrape the web into a bank',
    ['scrape', 'scraper', 'scrape into bank', 'scrape to bank', 'web', 'gallery',
     'gallery url', 'reddit', 'pexels', 'pornpics', 'civitai images', 'download',
     'download images', 'from the web', 'fill a bank', 'new bank from the web',
     'no folder', 'without a folder', 'add more images', 'resume scrape',
     'second scrape', 'append', 'grow a bank', 'destination', 'unfiltered',
     'no filter', 'keeps small images', 'small images kept', 'raw'],
    '/bank', 'using-the-app', 'the-image-bank-triage-a-big-folder'),
  setting('REDDIT_CLIENT_ID', 'scraping', 'REDDIT_CLIENT_ID', 'Reddit client ID',
    ['reddit', 'client id', 'scrape', '429', 'rate limit', 'quota', 'key']),
  setting('PEXELS_API_KEY', 'scraping', 'PEXELS_API_KEY', 'Pexels API key',
    ['pexels', 'api key', 'scrape', 'stock', 'key']),
  setting('klein.small_image_prompt', 'scraping', 'klein-small-image-prompt', 'Klein rescue — small scraped images',
    ['klein', 'small image', 'rescue', 'upscale', 'improve', 'prompt', 'scrape']),
  // Searched for by what people TRIED and could not do: they pasted a RedGifs or
  // TikTok link into the image scraper and got "no images found", or they
  // downloaded clips by hand into a folder because nothing else was on offer.
  action('video-bank-scrape', 'Scrape the web into a video bank',
    ['scrape', 'scraper', 'scrape video', 'scrape videos', 'scrape into video bank',
     'download videos', 'download a clip', 'video from the web', 'videos from a url',
     'redgifs', 'tiktok', 'erome', 'picazor', 'x videos', 'twitter video',
     'no videos found', 'my video link is ignored', 'video items dropped',
     'fill a video bank', 'video bank without a folder', 'no folder',
     'new video bank from the web', 'add more clips', 'resume scrape',
     // People search for where the files END UP, and for the reassurance: the
     // scrape is the one thing in this lane that adds to a folder of your own.
     'where do the clips go', 'which folder', 'add to my own bank',
     'scrape into an existing bank', 'add clips to my rushes folder',
     'does it write to my folder', 'my rushes folder',
     'bank not in the list', 'dataset folder'],
    '/video-bank', 'using-the-app', 'the-video-bank-turn-a-folder-of-rushes-into-shots'),
];
