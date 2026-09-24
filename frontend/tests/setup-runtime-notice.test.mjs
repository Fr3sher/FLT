import assert from 'node:assert/strict'
import test from 'node:test'
import { renderToStaticMarkup, createElement } from './support/mountJsx.mjs'
import { installCompletion, installRuntimeNotice } from '../src/components/setup/installRuntimeNotice.js'

const { InstallRuntimeNotice } = await import('../src/components/setup/InstallRunner.jsx')
const receipt = (overrides = {}) => ({
  profile: 'scoring', managed_installed: true, managed_python: '/managed/python',
  effective_python: '/external/python', uses_managed: false, selected_imports_ok: true,
  compute_tested: false, selection_failed: false, ...overrides,
})
const render = (notice) => renderToStaticMarkup(createElement(InstallRuntimeNotice, {
  result: installRuntimeNotice(notice), onChoose: () => {},
}))

for (const profile of ['scoring', 'semantic']) {
  test(`${profile}: a repair prominently names the unchanged external selection`, () => {
    const notice = receipt({ profile })
    const html = render(notice)
    assert.match(html, /Managed environment installed \/ repaired/)
    assert.match(html, /selected external Python was kept unchanged/)
    assert.match(html, /Both Python environments passed their import checks/)
    assert.match(html, /No calculation was tested/)
    assert.match(html, /Selected at the end of this repair/)
    assert.match(html, /\/external\/python/)
    assert.match(html, /\/managed\/python/)
    assert.match(html, /<button[^>]*>Choose Python \/ test calculation<\/button>/)
    const toast = installCompletion('success', notice)
    assert.equal(toast.tone, 'info')
    assert.match(toast.message, /selected external Python is unchanged/)
  })
}

test('an external import failure offers selection instead of reinstalling the same environment', () => {
  const notice = receipt({ selected_imports_ok: false })
  const html = render(notice)
  assert.match(html, /Its import check failed/)
  assert.match(html, /managed Python passed its import check/)
  assert.equal(installRuntimeNotice(notice).errorIsSelection, true)
  assert.match(installCompletion('error', notice).message, /Choose a Python/)
  assert.doesNotMatch(installCompletion('error', notice).message, /try again|Install failed/)
})

test('a managed selection distinguishes imports from a calculation test', () => {
  const notice = receipt({ uses_managed: true, effective_python: '/managed/python' })
  assert.match(render(notice), /Imports passed; calculation has not been tested/)
  assert.match(installCompletion('success', notice).message, /calculation not tested/)
  assert.equal(installRuntimeNotice(notice).warn, false)
})

test('unrelated installs and failed managed installs keep their ordinary feedback', () => {
  assert.equal(render(null), '')
  assert.equal(installRuntimeNotice(receipt({ managed_installed: false })), null)
  assert.equal(installRuntimeNotice(receipt({ profile: 'other' })), null)
  assert.deepEqual(installCompletion('success', null), { tone: 'success', message: 'Installed.' })
  assert.match(installCompletion('error', null).message, /Install failed/)
})
