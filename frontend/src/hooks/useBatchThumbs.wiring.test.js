// Wiring contract: the three high-volume grid surfaces batch their thumbnails
// through useBatchThumbs so a high-RTT link pays one round trip per batch, not
// one per tile. Source-pattern assertions (the repo's house style) pin the
// wiring so a refactor can't silently regress a surface back to per-image <img>.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const bankWs = readFileSync(new URL('../components/bank/BankWorkspace.jsx', import.meta.url), 'utf8');
const bankTile = readFileSync(new URL('../components/bank/BankTile.jsx', import.meta.url), 'utf8');
const resultsGrid = readFileSync(new URL('../components/dataset/studio/ResultsGrid.jsx', import.meta.url), 'utf8');
const resultTile = readFileSync(new URL('../components/dataset/studio/ResultTile.jsx', import.meta.url), 'utf8');
const concept = readFileSync(new URL('../components/dataset/ConceptSourcesPanel.jsx', import.meta.url), 'utf8');
const videoGrid = readFileSync(new URL('../components/videobank/VideoClipGrid.jsx', import.meta.url), 'utf8');

test('bank grid batches its thumbs through /bank/<id>/thumbs', () => {
  assert.match(bankWs, /import useBatchThumbs/);
  assert.match(bankWs, /\/api\/bank\/\$\{bankId\}\/thumbs/);
  assert.match(bankWs, /useBatchThumbs\(/);
  assert.match(bankWs, /thumbSrc=\{getThumb\(img\.id\)\}/);
});

test('bank tile still falls back to the single thumb on a missing blob', () => {
  assert.match(bankTile, /thumbSrc \|\| `\/api\/bank\/\$\{bankId\}\/thumb/);
});

test('studio results grid batches finished-tile thumbs through /dataset/<id>/thumbs', () => {
  assert.match(resultsGrid, /import useBatchThumbs/);
  assert.match(resultsGrid, /\/api\/dataset\/\$\{datasetId\}\/thumbs\?s=256/);
  assert.match(resultsGrid, /useBatchThumbs\(/);
  assert.match(resultsGrid, /thumbUrlFor=\{thumbUrlFor\}/);
  assert.match(resultTile, /thumbUrlFor\?\.\(cell\.filename\) \|\| `\/api\/dataset\/\$\{datasetId\}\/thumb/);
});

test('concept-source picker batches scraped thumbs through /scrape/thumbs', () => {
  assert.match(concept, /import useBatchThumbs/);
  assert.match(concept, /\/api\/scrape\/thumbs/);
  assert.match(concept, /useBatchThumbs\(/);
  assert.match(concept, /getScrapeThumb\(it\.thumbnail \|\| it\.url\) \|\| thumbFor\(it\)/);
});

test('video bank grid batches clip thumbs through /video-bank/<id>/clip-thumbs', () => {
  assert.match(videoGrid, /import useBatchThumbs/);
  assert.match(videoGrid, /\/api\/video-bank\/\$\{bankId\}\/clip-thumbs/);
  assert.match(videoGrid, /useBatchThumbs\(/);
  assert.match(videoGrid, /thumbUrlFor\(clip\.id\) \|\| videoClipThumbUrl/);
});
