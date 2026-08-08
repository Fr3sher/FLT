/**
 * A CONFIRMABLE cloud refusal must actually reach the user as a question.
 *
 * THE DEFECT, reported as "I still cannot run two trainings on the same dataset"
 * on an install whose backend supported it perfectly:
 *
 *   - the service refuses with a RuntimeError whose text starts `PARALLEL_RUN: `;
 *   - the route maps RuntimeError to HTTP 409 with `{error: "..."}` — a body that
 *     carries NO `ok` key;
 *   - `postJson` THROWS on any non-2xx instead of returning the body.
 *
 * The cloud launch retried on `d.ok === false`, so the await raised and the whole
 * retry was dead code. The user saw the raw refusal as an error toast, with the
 * question "Launch anyway?" printed at them and no way to answer it.
 *
 * The two neighbouring loops in the same file are NOT the same bug and are left
 * alone: they post through `postTrain`, which returns `{ok: false, error}` on a
 * non-2xx rather than throwing. One file, two clients, opposite error semantics —
 * which is exactly how the pattern got copied onto the wrong one.
 */
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

const { postWithConfirmations } = await import('../src/utils/trainingRefusals.js')

const refusal = (msg) => { const e = new Error(msg); e.status = 409; return e }

test('a thrown 409 refusal is answered and retried with the flag', async () => {
  const seen = []
  let calls = 0
  globalThis.window = { confirm: () => true }
  const post = async (body) => {
    seen.push({ ...body })
    if (++calls === 1) {
      throw refusal('PARALLEL_RUN: this dataset already has an active krea cloud '
        + 'run (#12) — launching another one rents a second pod. Launch anyway?')
    }
    return { ok: true, run_id: 13 }
  }
  const out = await postWithConfirmations(post, { gpu: 'A100' }, 'Train anyway (force)')
  assert.equal(out.run_id, 13, 'the second run never launched')
  assert.equal(seen[0].allow_parallel_run, undefined)
  assert.equal(seen[1].allow_parallel_run, true, 'the retry did not carry the confirmation')
})

test('declining does not launch anything', async () => {
  globalThis.window = { confirm: () => false }
  const post = async () => { throw refusal('PARALLEL_RUN: … Launch anyway?') }
  assert.equal(await postWithConfirmations(post, {}, 'Train anyway (force)'), null)
})

test('the cloud launch does not retry on a shape postJson never returns', () => {
  // The source check that keeps the defect from coming back by copy-paste: this
  // call site posts through postJson, which THROWS, so a `d.ok === false` loop
  // around it is unreachable no matter how right it looks.
  const src = readFileSync(
    new URL('../src/components/dataset/TrainingPanel.jsx', import.meta.url), 'utf8')
  // Bounded to launchCloud's OWN body: this file holds two other retry loops that
  // are correct (they post through postTrain, which returns instead of throwing)
  // and one more on the local lane, and a greedy slice would accuse all three.
  const cloud = src.slice(src.indexOf('const launchCloud'))
  const body = cloud.slice(0, cloud.indexOf('\n  };'))
  assert.match(body, /postWithConfirmations\(/,
    'the cloud launch must ask through the helper that catches the throw')
  assert.doesNotMatch(body, /d\.ok === false && \(flag = confirmableRetryFlag/,
    'a d.ok===false retry around postJson is dead code — postJson throws')
})
