// Parse untrusted JavaScript; never import/evaluate it. This is an authoring
// profile, not a security boundary against deliberately obfuscated trusted code.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';

try {
  const require = createRequire(path.join(process.argv[2], 'package.json'));
  const { parse } = require('acorn');
  const { scripts, files, workers = [] } = JSON.parse(readFileSync(0, 'utf8'));
  const workerLoaders = new Set(workers.flatMap(worker => worker.loaders));
  const usedLoaders = new Set();
  const included = new Set(files);
  const forbidden = new Set(['eval', 'Function', 'require']);
  for (const [filename, source] of Object.entries(scripts)) {
    const tree = parse(source, { ecmaVersion: 'latest', sourceType: 'module', locations: true });
    const globals = new Set(['globalThis', 'window', 'self', 'global']);
    const fail = (node, reason) => { throw new Error(`${filename}:${node.loc.start.line}: ${reason}`); };
    const dependency = (node, literal) => {
      if (!literal || literal.type !== 'Literal' || typeof literal.value !== 'string') {
        fail(node, 'Computed dynamic imports are outside the auditable package profile');
      }
      const spec = literal.value;
      if (!spec.startsWith('./') && !spec.startsWith('../')) {
        fail(node, 'Bundle external dependencies; host-private, bare and remote imports are forbidden');
      }
      if (/[\\:?#%]/.test(spec)) fail(node, 'Non-portable JavaScript import');
      const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(filename), spec));
      if (resolved.startsWith('../') || !included.has(resolved)) fail(node, 'Imported file is absent or outside the package');
    };
    const visit = (node, parent = null) => {
      if (!node || typeof node !== 'object') return;
      if (node.type === 'VariableDeclarator' && node.id.type === 'Identifier' &&
          node.init?.type === 'Identifier' && globals.has(node.init.name)) globals.add(node.id.name);
      if (node.type === 'ImportDeclaration' || node.type === 'ExportAllDeclaration' ||
          (node.type === 'ExportNamedDeclaration' && node.source)) dependency(node, node.source);
      if (node.type === 'ImportExpression') dependency(node, node.source);
      const typeCheck = node.name === 'Function' && parent?.type === 'BinaryExpression' &&
        parent.operator === 'instanceof' && parent.right === node;
      if (node.type === 'Identifier' && forbidden.has(node.name) && !typeCheck) fail(node, 'Dynamic code loading is outside the auditable package profile');
      if (node.type === 'MemberExpression' && node.computed) {
        const key = node.property;
        if (key.type === 'Literal' && forbidden.has(key.value)) fail(node, 'Dynamic code loading is outside the auditable package profile');
        if (node.object.type === 'Identifier' && globals.has(node.object.name) && key.type !== 'Literal') {
          fail(node, 'Computed global access is outside the auditable package profile');
        }
      }
      if (node.type === 'CallExpression' || node.type === 'NewExpression') {
        const name = node.callee.type === 'Identifier' ? node.callee.name : node.callee.property?.name;
        if (name === 'Worker') {
          if (node.type !== 'NewExpression' || !workerLoaders.has(filename)) {
            fail(node, 'Worker entry points require an explicit frontend_workers loader declaration');
          }
          usedLoaders.add(filename);
        }
        if (['SharedWorker', 'importScripts'].includes(name)) fail(node, 'Shared workers and imported worker scripts are outside the package profile');
        if (name === 'createElement' && node.arguments[0]?.value?.toLowerCase?.() === 'script') {
          fail(node, 'DOM script loading is outside the auditable package profile');
        }
        if (['setTimeout', 'setInterval'].includes(name) && typeof node.arguments[0]?.value === 'string') {
          fail(node, 'String timers execute dynamic code outside the auditable package profile');
        }
      }
      for (const [key, value] of Object.entries(node)) {
        if (key === 'loc') continue;
        if (Array.isArray(value)) value.forEach(child => visit(child, node));
        else if (value && typeof value === 'object') visit(value, node);
      }
    };
    visit(tree);
  }
  if ([...workerLoaders].some(loader => !usedLoaders.has(loader))) throw new Error('A declared worker loader does not create a Worker');
  process.stdout.write(JSON.stringify({ ok: true }));
} catch (error) {
  process.stdout.write(`JavaScript audit: ${error.message}`);
  process.exitCode = 1;
}
