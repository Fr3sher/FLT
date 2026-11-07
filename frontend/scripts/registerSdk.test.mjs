import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
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

test('declared SDK build dependencies resolve from the host without an SDK node_modules', t => {
  // Recreate the CI layout outside the checkout, so an existing local SDK
  // installation cannot make a missing host-resolution hook pass this test.
  const root = mkdtempSync(path.join(os.tmpdir(), 'lds-sdk-loader-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const sdk = path.join(root, 'sdk', 'frontend')
  const host = path.join(root, 'frontend')
  mkdirSync(sdk, { recursive: true })
  mkdirSync(path.join(host, 'scripts'), { recursive: true })
  const pkg = JSON.parse(readFileSync(new URL('../../sdk/frontend/package.json', import.meta.url), 'utf8'))
  const names = Object.keys(pkg.dependencies)
  writeFileSync(path.join(sdk, 'package.json'), JSON.stringify({ ...pkg, exports: { '.': './probe.mjs' } }))
  writeFileSync(path.join(host, 'package.json'), JSON.stringify({ type: 'module' }))
  copyFileSync(new URL('./registerSdk.mjs', import.meta.url), path.join(host, 'scripts', 'registerSdk.mjs'))
  for (const name of names) {
    const directory = path.join(host, 'node_modules', name)
    mkdirSync(directory, { recursive: true })
    writeFileSync(path.join(directory, 'package.json'), JSON.stringify({ name, main: 'index.cjs' }))
    writeFileSync(path.join(directory, 'index.cjs'), `module.exports = ${JSON.stringify({ name, source: 'host' })}`)
  }
  writeFileSync(path.join(sdk, 'probe.mjs'), `
    import assert from 'node:assert/strict';
    import { createRequire } from 'node:module';
    const require = createRequire(import.meta.url);
    for (const name of ${JSON.stringify(names)}) {
      const imported = (await import(name)).default;
      assert.deepEqual(imported, { name, source: 'host' });
      assert.strictEqual(require(name), imported);
    }
  `)
  assert.equal(existsSync(path.join(sdk, 'node_modules')), false)
  const child = spawnSync(process.execPath, [
    '--import', pathToFileURL(path.join(host, 'scripts', 'registerSdk.mjs')).href,
    '--input-type=module', '--eval', "await import('@lds/plugin-sdk')",
  ], { cwd: sdk, encoding: 'utf8', timeout: 30000 })
  assert.equal(child.status, 0, child.error?.message || child.stderr || child.stdout)
})
