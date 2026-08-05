/**
 * Contract for ✨ Score's two intents.
 *
 * The trap this pins is a repeat of one already made on the neighbouring pass:
 * "make the pass resume" reads like "hand it only the unscored images", and the
 * button that used to mean "do the whole bank" then becomes a no-op that still
 * reports a success. Here it would be worse than a no-op, because the style
 * cluster ids are ONE numbering of the whole bank — a pass over a subset would
 * restart them at 1 and land them on unrelated groups already stored.
 *
 * So three things are pinned, across both sides of the wire:
 *   • ✨ Score keeps posting an EMPTY body — it never silently re-scores;
 *   • the recompute-everything intent is a SEPARATE, explicit button, offered
 *     only when there is something to recompute (same shape as "Rescan all");
 *   • the server's pool stays "every non-rejected image", with no
 *     "already scored" filter anywhere near it.
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// CRLF-normalised: these files are checked out with native line endings on
// Windows and every pattern below spans lines.
const read = (rel) => readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const workspace = read('../src/components/bank/BankWorkspace.jsx')
const route = read('../../backend/app/routes/bank.py')
const service = read('../../backend/app/services/image_bank_service.py')

test('the ✨ Score button posts nothing extra — its meaning is unchanged', () => {
  assert.match(workspace,
    /const startScore = \(rescore\) => act\(\s*\(\) => postJson\(`\/api\/bank\/\$\{bankId\}\/score`, rescore \? \{ rescore: true \} : \{\}\)/)
  assert.match(workspace, /onClick=\{\(\) => startScore\(false\)\}/)
})

test('"Rescore all" is a separate intent, shown only when there is something to redo', () => {
  const m = workspace.match(/\{scored > 0 && caps\.bank_scoring && \([\s\S]{0,600}?Rescore all/)
  assert.ok(m, 'the Rescore all button must be gated on scored > 0')
  assert.match(m[0], /onClick=\{\(\) => startScore\(true\)\}/)
  // Its price is stated where the user hovers — a full pass is not free.
  assert.match(m[0], /ignoring the cached embeddings/)
  assert.match(m[0], /Costs a full pass/)
})

test('the plain ✨ Score button tells the user a relaunch is cheap', () => {
  // The whole point of the resume is invisible unless it is said: without this
  // sentence people stop a long pass expecting to lose everything.
  assert.match(workspace,
    /Already-scored images are reused, so stopping and relaunching costs only what is left/)
})

test('the server reads the intent from the body and nowhere else', () => {
  assert.match(route,
    /def bank_score\(bank_id\):[\s\S]{0,600}?rescore=bool\(data\.get\('rescore'\)\)/)
  assert.match(service, /def start_score\(app, user_id, bank_id, rescore=False\):/)
})

test('the scoring pool is never narrowed to "not scored yet"', () => {
  const job = service.slice(service.indexOf('def _score_job(bank_id'),
    service.indexOf("'rescore': bool(rescore)"))
  assert.ok(job.length > 0)
  assert.match(job, /\.filter\(BankImage\.status != 'reject'\)/)
  // A per-image score column appearing in this query is exactly the regression:
  // it would shrink the payload the style clustering is computed from.
  assert.doesNotMatch(job, /aesthetic_score/)
  assert.doesNotMatch(job, /nsfw_score/)
  assert.doesNotMatch(job, /style_cluster\.is_\(None\)/)
})

test('a stopped pass writes scores but never a half style partition', () => {
  // Both halves matter and they pull in opposite directions, so both are pinned
  // here: the salvage write must NOT honour the (already set) cancel flag, and
  // the cluster write must NOT run when the write-back was interrupted.
  assert.match(service,
    /_apply_score_results\(\s*job, by_path, data\['results'\], interruptible=False\)/)
  assert.match(service,
    /if stopped:[\s\S]{0,400}?Stopped while saving[\s\S]{0,400}?return\n\s+_write_style_clusters/)
})
