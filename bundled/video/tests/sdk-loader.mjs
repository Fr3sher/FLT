const fixtures = {
  '@lds/plugin-sdk/help': './sdk-fixtures/help.js',
  '@lds/plugin-sdk/bank': './sdk-fixtures/bank.js',
  '@lds/plugin-sdk/search': './sdk-fixtures/search.js',
  '@lds/plugin-sdk/data': './sdk-fixtures/data.js',
  'lucide-react': './sdk-fixtures/icons.js',
}
export async function resolve(specifier, context, nextResolve) {
  if (Object.hasOwn(fixtures, specifier))
    return { url: new URL(fixtures[specifier], import.meta.url).href, shortCircuit: true }
  return nextResolve(specifier, context)
}
