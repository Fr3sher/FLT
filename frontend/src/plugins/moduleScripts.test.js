import test from 'node:test'
import assert from 'node:assert/strict'
import { loadModuleScript, mountModuleScript } from './moduleScripts.js'

const documentWith = (appendChild) => ({
  baseURI: 'http://localhost/', createElement: () => ({ dataset: {} }), head: { appendChild },
})

test('a failed module load answers a bounded failure', async () => {
  const doc = documentWith((element) => queueMicrotask(() => element.onerror()))
  assert.deepEqual(await loadModuleScript('/broken.js', 100, doc), { ok: false, why: 'failed to load' })
})

test('a silent module cannot block application boot forever', async () => {
  const doc = documentWith(() => {})
  assert.deepEqual(await loadModuleScript('/silent.js', 1, doc), { ok: false, why: 'timed out after 1 ms' })
})

test('an invalid URL or a failed DOM insertion never rejects the loader', async () => {
  const doc = documentWith(() => { throw new Error('DOM unavailable') })
  assert.deepEqual(await loadModuleScript('http://[', 100, doc), { ok: false, why: 'failed to mount' })
  assert.deepEqual(await loadModuleScript('/valid.js', 100, doc), { ok: false, why: 'failed to mount' })
})

test('absolute and relative spellings of the same script share one entry', () => {
  const appended = []
  const doc = documentWith((element) => appended.push(element))
  assert.equal(mountModuleScript('/entry.js', doc).created, true)
  assert.equal(mountModuleScript('http://localhost/entry.js', doc).created, false)
  assert.equal(appended.length, 1)
})
