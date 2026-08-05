import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const workspace = readFileSync(new URL('./DatasetWorkspace.jsx', import.meta.url), 'utf8')

test('Dataset to Bank copy has a named, count-aware activity banner', () => {
  assert.match(workspace, /bank_export: `Copying into a Bank…\$\{prog\}`/)
})

test('Dataset to Bank copy never claims that it pauses ComfyUI', () => {
  assert.match(workspace, /\|\| act\.kind === 'bank_export'/)
})
