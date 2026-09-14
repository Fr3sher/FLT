import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

test('SDK test loader shares host packages for ESM and require without re-entering itself', () => {
  // Use an actual child loader, including Node's require.resolve hooks. A pure
  // resolver mock missed their re-entrant behavior introduced in Node 24.20.
  const host = new URL('../package.json', import.meta.url).href
  const plugin = new URL('../../bundled/canvas/package.json', import.meta.url).href
  const child = spawnSync(process.execPath, [
    '--import', new URL('./registerSdk.mjs', import.meta.url).href,
    '--input-type=module', '--eval', `
      import assert from 'node:assert/strict';
      import { createRequire } from 'node:module';
      const host = createRequire(${JSON.stringify(host)});
      const plugin = createRequire(${JSON.stringify(plugin)});
      for (const name of ['react', 'react/jsx-runtime', 'react-dom/server', 'react-router', 'lucide-react']) {
        assert.ok(host.resolve(name), name);
        assert.strictEqual(plugin(name), host(name), name);
        assert.ok(await import(name), name);
      }
      assert.strictEqual((await import('react')).default, host('react'));
      assert.equal(typeof (await import('@lds/plugin-sdk')).registerPlugin, 'function');
      assert.equal(typeof (await import('@lds/plugin-sdk/data')).checkpointFileLabel, 'function');
      await assert.rejects(import('@lds/plugin-sdk/not-exported'), /Unknown public LDS SDK export/);
      await assert.rejects(import('react/not-exported'), { code: 'ERR_PACKAGE_PATH_NOT_EXPORTED' });
    `,
  ], {
    cwd: fileURLToPath(new URL('../../sdk/frontend/', import.meta.url)),
    encoding: 'utf8', timeout: 30000,
  })
  assert.equal(child.status, 0, child.error?.message || child.stderr || child.stdout)
})
