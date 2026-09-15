import assert from 'node:assert/strict'
import test from 'node:test'
import { MemoryRouter } from 'react-router'
import { createElement, render } from './support/mountJsx.mjs'

const { default: BankPassesPanel } = await import('../src/components/bank/BankPassesPanel.jsx')
const { semanticEngineState } = await import('../src/components/bank/bankSemanticEngine.js')
const noop = () => {}
const RoutedPanel = (props) => createElement(MemoryRouter, null, createElement(BankPassesPanel, props))

function panel(overrides = {}) {
  const payload = { counts: { total: 2, keep: 2 }, semantic: {
    engine: 'siglip2', ready: true, counts: { total: 2, ok: 2 },
    device: { requested: 'auto', device: 'cuda', gpu: true },
  } }
  return render(RoutedPanel, {
    bankId: 1, payload, counts: payload.counts, live: false,
    caps: { bank_scoring: true, bank_siglip2: true }, capsLoading: false,
    semanticState: semanticEngineState(payload, { bank_siglip2: true }),
    semanticReady: true, semanticSwitching: false, semanticOperationBusy: false,
    scoreGpuPresent: true, scoreDevice: { device: 'cuda', gpu: true }, scoreNote: null,
    selected: new Set(), captionScope: '', captionVocab: 'neutral',
    onPickPython: noop, onPassOpen: noop, onPassRedo: noop,
    onSemanticEngineChange: noop, onChanged: noop, ...overrides,
  })
}

function managementButtons(html) {
  return [...html.matchAll(/<button\b([^>]*)>(Manage (?:Score|SigLIP 2) Python…)<\/button>/g)]
}

test('CUDA detection never hides either Python recovery action', () => {
  const buttons = managementButtons(panel())
  assert.equal(buttons.length, 2)
  for (const button of buttons) assert.doesNotMatch(button[1], /\sdisabled=/)
})

test('both actions remain discoverable while capabilities load and while CPU-only', () => {
  for (const overrides of [{ capsLoading: true }, { caps: {}, scoreGpuPresent: false }]) {
    assert.equal(managementButtons(panel(overrides)).length, 2)
  }
})

test('an active pass keeps both actions visible but disabled', () => {
  const buttons = managementButtons(panel({ live: true }))
  assert.equal(buttons.length, 2)
  for (const button of buttons) assert.match(button[1], /disabled=""/)
})
