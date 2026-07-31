import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(
  new URL('./LocalToolsSection.jsx', import.meta.url), 'utf8')
const primitives = readFileSync(
  new URL('./primitives.jsx', import.meta.url), 'utf8')

test('dense cloud uses its own clearly scoped HF secret field', () => {
  assert.match(source, /key:\s*'HF_CLOUD_TOKEN'/)
  assert.match(source, /Dedicated Hugging Face cloud token/)
  assert.match(source, /separate fine-grained token/)
  assert.match(source, /zero global permissions/)
  assert.match(source, /repo\.content\.read exactly on krea\/Krea-2-Raw/)
  assert.match(source, /repo\.content\.read \+ repo\.write on one dedicated HF user\/org namespace/)
  assert.match(source, /contains only LDS deliveries/)
  assert.match(source, /per-run repository does not exist yet/)
  assert.doesNotMatch(source, /only its private delivery repositories/)
  assert.match(source, /Never reuse a broad or general HF token/)
  assert.match(source, /<SecretField field=\{HF_CLOUD_SECRET\}/)
  assert.match(source, /<SecretField field=\{HF_SECRET\}/)
})

test('focus=HF_CLOUD_TOKEN lands on the secret input id', () => {
  assert.match(primitives, /id=\{f\.key\}/)
  assert.match(primitives, /htmlFor=\{f\.key\}/)
})
