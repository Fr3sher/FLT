import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
// Babel's parser is already locked with the application's React Vite plugin.
const { parse } = require('@babel/parser')
const bundled = fileURLToPath(new URL('../../bundled/', import.meta.url))
function files(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const value = path.join(directory, entry.name)
    return entry.isDirectory() ? files(value) : /\.[jt]sx?$/.test(entry.name) ? [value] : []
  })
}
function imports(node, out = []) {
  if (!node || typeof node !== 'object') return out
  if (['ImportDeclaration', 'ExportNamedDeclaration', 'ExportAllDeclaration', 'ImportExpression'].includes(node.type)
    && typeof node.source?.value === 'string') out.push(node.source.value)
  if (node.type === 'CallExpression' && node.callee?.type === 'Import' && typeof node.arguments[0]?.value === 'string') {
    out.push(node.arguments[0].value)
  }
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach((child) => imports(child, out))
    else if (value && typeof value === 'object') imports(value, out)
  }
  return out
}

test('every packaged frontend imports only its package, declared libraries and public SDK', () => {
  const checked = []
  for (const name of readdirSync(bundled)) {
    const root = path.join(bundled, name)
    const pkgFile = path.join(root, 'package.json')
    if (!existsSync(pkgFile)) continue
    const pkg = JSON.parse(readFileSync(pkgFile, 'utf8'))
    if (!pkg.lds?.sdk) continue
    const allowed = new Set(['react', 'react-dom', 'react-router', '@lds/plugin-sdk', ...Object.keys(pkg.dependencies || {})])
    for (const file of files(path.join(root, 'frontend'))) {
      const ast = parse(readFileSync(file, 'utf8'), { sourceType: 'module', plugins: ['jsx'] })
      for (const source of imports(ast)) {
        const label = `${name}/${path.relative(root, file)}: ${source}`
        if (source.startsWith('.')) {
          const resolved = path.resolve(path.dirname(file), source)
          assert.ok(resolved.startsWith(root + path.sep), `Import escapes plugin: ${label}`)
        } else {
          const dependency = source.startsWith('@') ? source.split('/').slice(0, 2).join('/') : source.split('/')[0]
          assert.ok(allowed.has(dependency), `Undeclared dependency or private host import: ${label}`)
        }
      }
    }
    checked.push(name)
  }
  assert.ok(checked.includes('camera_angles'), 'the independent Camera pilot stays covered')
})
