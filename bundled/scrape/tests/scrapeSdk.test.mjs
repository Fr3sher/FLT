import assert from 'node:assert/strict'
import test from 'node:test'
import { missingScrapeDeps, scrapeDepsBanner } from '../frontend/lib/scrapeDeps.js'

test('the packaged readiness message follows the actual probe instead of a fixed dependency list', () => {
  assert.deepEqual(missingScrapeDeps('probe failed; missing: ddgs, yt_dlp, curl_cffi'), ['ddgs', 'yt_dlp', 'curl_cffi'])
  assert.match(scrapeDepsBanner('missing: ddgs, yt_dlp'), /ddgs, yt_dlp/)
  assert.doesNotMatch(scrapeDepsBanner(null), /curl_cffi|ddgs|yt_dlp/)
})
