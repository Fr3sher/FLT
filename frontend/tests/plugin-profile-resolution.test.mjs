import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const importer = fileURLToPath(new URL('../src/main.jsx', import.meta.url))

test('Vite resolves the actual host entry to the selected plugin profile', async () => {
  const previous = process.env.LDS_PLUGIN_BUILD_MODE
  try {
    for (const [mode, expected] of [['bundled', 'bundledDevelopment.js'], ['store', 'bundled.js']]) {
      process.env.LDS_PLUGIN_BUILD_MODE = mode
      const server = await createServer({ root, server: { middlewareMode: true }, watch: null })
      try {
        const resolved = await server.pluginContainer.resolveId('./plugins/bundled', importer)
        assert.ok(resolved.id.replaceAll('\\', '/').endsWith(`/src/plugins/${expected}`), resolved.id)
      } finally {
        await server.close()
      }
    }
  } finally {
    if (previous === undefined) delete process.env.LDS_PLUGIN_BUILD_MODE
    else process.env.LDS_PLUGIN_BUILD_MODE = previous
  }
})
