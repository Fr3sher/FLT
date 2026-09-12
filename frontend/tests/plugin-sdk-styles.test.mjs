import assert from 'node:assert/strict'
import test from 'node:test'
import postcss from 'postcss'
import { namespaceUtilities, styleRuntimeSource } from '../../sdk/frontend/styles.mjs'

test('late plugin utilities never contain a host utility class selector', () => {
  const root = postcss.parse('.flex{display:flex}.group:hover .group-hover\\:block{display:block}@media(min-width:768px){.md\\:hidden{display:none}}')
  const result = namespaceUtilities(root, 'camera_angles')
  assert.match(result.css, /\.lds-camera_angles-flex/)
  assert.match(result.css, /\.lds-camera_angles-group:hover/)
  assert.match(result.css, /\.lds-camera_angles-md\\:hidden/)
  assert.doesNotMatch(result.css, /(?:^|\s|\{|,)\.flex[\s{]/)
  assert.deepEqual(result.classes, ['flex', 'group', 'group-hover:block', 'md:hidden'])
})

test('resolved dynamic classes and portal props are namespaced without changing data', async () => {
  const source = styleRuntimeSource({ prefix: 'lds-camera-', classes: ['flex', 'md:hidden'] })
  const { scopeProps } = await import('data:text/javascript,' + encodeURIComponent(source))
  const props = { className: ['flex', false, 'md:hidden'].filter(Boolean).join(' '), title: 'flex', 'data-state': 'hidden' }
  assert.deepEqual(scopeProps(props), { ...props, className: 'lds-camera-flex lds-camera-md:hidden' })
  assert.equal(props.className, 'flex md:hidden')
  assert.equal(scopeProps(null), null)
  assert.deepEqual(scopeProps({ className: 'shared-widget' }), { className: 'shared-widget' })
  assert.deepEqual(scopeProps(scopeProps(props)), scopeProps(props))
})
