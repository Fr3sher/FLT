import { readFileSync } from 'node:fs'
const sdk = JSON.parse(readFileSync(new URL('../../../sdk/frontend/package.json', import.meta.url)))
const fixtures = {
  '@lds/plugin-sdk/help': './sdk-fixtures/help.js',
  '@lds/plugin-sdk/bank': './sdk-fixtures/bank.js',
  '@lds/plugin-sdk/search': './sdk-fixtures/search.js',
  '@lds/plugin-sdk/data': './sdk-fixtures/data.js',
  'lucide-react': './sdk-fixtures/icons.js',
}
export async function resolve(specifier, context, nextResolve) {
  if (specifier === '@lds/plugin-sdk')
    return { url: new URL('../../../sdk/frontend/runtime.js', import.meta.url).href, shortCircuit: true }
  if (specifier === '@lds/plugin-sdk/links')
    return { url: new URL('../../../sdk/frontend/links.js', import.meta.url).href, shortCircuit: true }
  if (Object.hasOwn(fixtures, specifier))
    return { url: new URL(fixtures[specifier], import.meta.url).href, shortCircuit: true }
  if (specifier.startsWith('@lds/plugin-sdk/')) {
    const target = sdk.exports[`./${specifier.slice('@lds/plugin-sdk/'.length)}`]
    if (target) return { url: new URL(`../../../sdk/frontend/${target}`, import.meta.url).href, shortCircuit: true }
  }
  return nextResolve(specifier, context)
}
