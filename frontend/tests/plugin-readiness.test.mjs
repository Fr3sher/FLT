import assert from 'node:assert/strict'
import test from 'node:test'
import { resetRegistry, registerDescriptor, setEnabled } from '../src/plugins/registry.js'
import { productReadiness } from '../src/plugins/readiness.js'

test('active product keeps missing and waiting components visible beside working ones', (t) => {
  resetRegistry()
  t.after(resetRegistry)
  registerDescriptor({ id: 'example.tools', slots: { 'setup.step': [{ id: 'models', rows: caps => [
    { label: 'Model', ok: caps.model }, { label: 'Local service', pending: true, note: 'Start the service.' },
    { label: 'Optional tool', ok: false },
  ] }] } })
  setEnabled(['example.tools'])
  assert.deepEqual(productReadiness('example.tools', { model: true }).map(row => row.state), ['ready', 'pending', 'setup'])
  setEnabled([])
  assert.deepEqual(productReadiness('example.tools', { model: true }), [])
})

test('one failed product readiness reader does not certify readiness or break the store', (t) => {
  resetRegistry()
  t.after(resetRegistry)
  registerDescriptor({ id: 'example.tools', slots: { 'setup.step': [{ id: 'failed', rows: () => { throw Error('probe unavailable') } }] } })
  setEnabled(['example.tools'])
  assert.equal(productReadiness('example.tools', {}).at(0).state, 'unknown')
})
