import assert from 'node:assert/strict';
import test from 'node:test';
import { readinessHint, summarize } from './bankTextSearch.js';

test('refined results identify both stages without describing cosines as their order', () => {
  const text = summarize({
    engine: 'siglip2', query: 'a landscape', pool: 100, image_ids: [2, 1],
    score_range: { top: .9, bottom: .1 }, pool_median: .2,
    reranking: { count: 20 },
  });
  assert.match(text, /Qwen refined the first 20/);
  assert.match(text, /SigLIP/);
  assert.doesNotMatch(text, /Similarity .*down to|tail is much weaker/);
  assert.match(text, /does not select/);
});

test('warm retrieval does not promise instant Qwen refinement', () => {
  const text = readinessHint({ available: true, warm: true }, 'siglip2', true);
  assert.match(text, /every search, including repeated phrases/);
  assert.doesNotMatch(text, /instant/);
  assert.equal(readinessHint({ available: false, reason: 'Missing index' }, 'siglip2', true), 'Missing index');
});
