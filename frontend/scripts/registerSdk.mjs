// Resolve the public SDK package in repository tests without installing a
// second dependency tree. Distributed plugins resolve its npm package normally.
import { createRequire, registerHooks } from 'node:module'
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
const base = new URL('../../sdk/frontend/', import.meta.url)
const pkg = JSON.parse(readFileSync(new URL('package.json', base), 'utf8'))
const hostRequire = createRequire(new URL('../package.json', import.meta.url))
const sharedPackages = new Set(['react', 'react-dom', 'react-router', 'lucide-react'])
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (sharedPackages.has(specifier.split('/')[0])) {
      return { url: pathToFileURL(hostRequire.resolve(specifier)).href, shortCircuit: true }
    }
    if (specifier === '@lds/plugin-sdk' || specifier.startsWith('@lds/plugin-sdk/')) {
      const key = specifier === '@lds/plugin-sdk' ? '.' : `.${specifier.slice('@lds/plugin-sdk'.length)}`
      if (!pkg.exports[key]) throw new Error(`Unknown public LDS SDK export: ${specifier}`)
      return { url: new URL(pkg.exports[key], base).href, shortCircuit: true }
    }
    return nextResolve(specifier, context)
  },
})
