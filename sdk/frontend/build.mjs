#!/usr/bin/env node
import path from 'node:path'
import { readFile, mkdir, writeFile, realpath, readdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
import { build } from 'vite'
import postcss from 'postcss'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'
import theme from './theme.js'
import { namespaceUtilities, styleRuntimeSource } from './styles.mjs'

const SDK_ROOT = path.dirname(fileURLToPath(import.meta.url))
const SDK_PACKAGE = JSON.parse(await readFile(new URL('./package.json', import.meta.url), 'utf8'))
const REACT_EXPORTS = ['Children', 'Component', 'Fragment', 'Profiler', 'PureComponent', 'StrictMode', 'Suspense',
  'cache', 'cloneElement', 'createContext', 'createElement', 'createRef', 'forwardRef', 'isValidElement', 'lazy',
  'memo', 'startTransition', 'use', 'useActionState', 'useCallback', 'useContext', 'useDebugValue',
  'useDeferredValue', 'useEffect', 'useId', 'useImperativeHandle', 'useInsertionEffect', 'useLayoutEffect',
  'useMemo', 'useOptimistic', 'useReducer', 'useRef', 'useState', 'useSyncExternalStore', 'useTransition', 'version']
const SHARED = {
  react: ['React', REACT_EXPORTS, true],
  'react/jsx-runtime': ['ReactJSXRuntime', ['Fragment', 'jsx', 'jsxs'], false],
  'react-dom/client': ['ReactDOM', ['createRoot', 'hydrateRoot'], false],
  'react-dom': ['ReactDOMPortal', ['createPortal', 'flushSync'], false],
  'react-router': ['router', ['Link', 'NavLink', 'useLocation', 'useNavigate', 'useParams', 'useSearchParams'], false],
}
const inside = (child, parent) => {
  const candidate = path.resolve(child)
  const anchor = path.resolve(parent)
  return candidate === anchor || candidate.startsWith(`${anchor}${path.sep}`)
}

/** Build only a plugin and its declared dependencies. No LDS checkout needed. */
export async function buildPlugin({ plugin, outDir }) {
  const root = await realpath(path.resolve(plugin))
  const out = path.resolve(outDir)
  if (out === root || inside(root, out)) throw new Error('Output must not contain the plugin source directory.')
  try {
    if ((await readdir(out)).length) throw new Error('Plugin output must be empty; use a new build directory.')
  } catch (error) { if (error.code !== 'ENOENT') throw error }
  const manifest = JSON.parse(await readFile(path.join(root, 'plugin.json'), 'utf8'))
  const utilities = await postcss([tailwindcss({ ...theme, content: [path.join(root, 'frontend/**/*.{js,jsx,ts,tsx}').replaceAll('\\', '/')] }), autoprefixer()])
    .process('@tailwind utilities;', { from: undefined })
  const styles = namespaceUtilities(utilities.root, manifest.id)
  const packagePath = path.join(root, 'package.json')
  const packageJson = JSON.parse(await readFile(packagePath, 'utf8'))
  const entry = await realpath(path.resolve(root, packageJson.lds?.entry || 'frontend/index.js'))
  if (!inside(entry, root)) throw new Error('The frontend source entry must stay inside the plugin package.')
  const virtualEntry = '\0lds:plugin-entry'
  const entryPath = path.join(root, '__lds_plugin_entry__.js').replaceAll('\\', '/')
  const dependencies = new Set(Object.keys(packageJson.dependencies || {}))
  const workerDeclarations = packageJson.lds?.workers || []
  if (!Array.isArray(workerDeclarations) || workerDeclarations.length > 10) throw new Error('lds.workers must be a short list.')
  const require = createRequire(packagePath)
  const workers = []
  for (const declaration of workerDeclarations) {
    if (!declaration || Object.keys(declaration).some(key => !['entry', 'loader'].includes(key))) throw new Error('Invalid worker declaration.')
    const paths = {}
    for (const key of ['entry', 'loader']) {
      const specifier = declaration[key]
      if (typeof specifier !== 'string' || /[\\\\:?#%]/.test(specifier) || specifier.split('/').includes('..')) throw new Error('Use a declared dependency worker and loader.')
      const name = specifier.startsWith('@') ? specifier.split('/').slice(0, 2).join('/') : specifier.split('/')[0]
      if (!dependencies.has(name)) throw new Error('Worker files must belong to declared dependencies.')
      paths[key] = await realpath(require.resolve(specifier))
      if (!inside(paths[key], root)) throw new Error('Worker files must stay inside the plugin package.')
    }
    workers.push({ ...paths, bytes: await readFile(paths.entry) })
  }
  const frontendWorkers = []
  const moduleNames = []
  const result = await build({
    configFile: false, root, base: './', publicDir: false,
    esbuild: { jsx: 'automatic', jsxImportSource: 'react' },
    plugins: [{
      name: 'lds-public-plugin-contract',
      enforce: 'pre',
      resolveId(source, importer) {
        if (source === '\0lds:style-runtime') return source
        if (source === virtualEntry || source.replaceAll('\\', '/') === entryPath) return virtualEntry
        if (/\.css(?:\?|$)/.test(source)) throw new Error('Use the SDK utility style profile; global CSS imports cannot be isolated safely.')
        if (SHARED[source]) return `\0lds:shared:${source}`
        if (source === '@lds/plugin-sdk' || source.startsWith('@lds/plugin-sdk/')) {
          const key = source === '@lds/plugin-sdk' ? '.' : `.${source.slice('@lds/plugin-sdk'.length)}`
          const target = SDK_PACKAGE.exports[key]
          if (!target || key === './build') throw new Error(`Not a browser SDK export: ${source}`)
          return path.join(SDK_ROOT, target)
        }
        if (source.startsWith('.') && importer && !importer.startsWith('\0')) {
          const target = path.resolve(path.dirname(importer), source)
          if (!inside(target, root) && !inside(target, SDK_ROOT)) {
            throw new Error(`Plugin import leaves its package: ${source}`)
          }
        }
        if (!source.startsWith('.') && !source.startsWith('\0') && !path.isAbsolute(source)) {
          const name = source.startsWith('@') ? source.split('/').slice(0, 2).join('/') : source.split('/')[0]
          if (!dependencies.has(name) && !String(importer).replaceAll('\\', '/').includes('/node_modules/')) {
            throw new Error(`Undeclared plugin dependency: ${name}`)
          }
        }
        return null
      },
      load(id) {
        if (id === '\0lds:style-runtime') return styleRuntimeSource(styles)
        if (id === virtualEntry) return `import descriptor from ${JSON.stringify(entry)};\n`
          + `import { registerPlugin } from '@lds/plugin-sdk';\n`
          + `registerPlugin({...descriptor, version:${JSON.stringify(manifest.version)}});\n`
        if (!id.startsWith('\0lds:shared:')) return null
        const [field, names, isDefault] = SHARED[id.slice('\0lds:shared:'.length)]
        const wrapped = field === 'ReactJSXRuntime' ? new Set(['jsx', 'jsxs'])
          : field === 'React' ? new Set(['createElement', 'cloneElement']) : new Set()
        return `import { runtime } from '@lds/plugin-sdk';\nimport { scopeProps } from '\\0lds:style-runtime';\nconst shared=runtime()[${JSON.stringify(field)}];\n`
          + `if (!shared) throw new Error('Required LDS shared runtime is unavailable');\n`
          + names.map((name) => `export const ${name}=` + (wrapped.has(name)
            ? `(type,props,...rest)=>shared.${name}(type,scopeProps(props),...rest);`
            : `shared.${name};`)).join('\n')
          + (isDefault ? '\nexport default {...shared,createElement,cloneElement};' : '')
      },
      generateBundle(_options, bundle) {
        for (const id of this.getModuleIds()) {
          if (id.startsWith('\0')) { moduleNames.push(id.slice(1)); continue }
          const clean = id.split('?')[0]
          if (/\/node_modules\/(react|react-dom|react-router)\//.test(clean.replaceAll('\\', '/'))) {
            throw new Error('A plugin must use the host React and router runtimes, not bundle another copy.')
          }
          if (inside(clean, root)) { moduleNames.push(path.relative(root, clean).replaceAll('\\', '/')); continue }
          if (inside(clean, SDK_ROOT)) { moduleNames.push(`sdk/${path.relative(SDK_ROOT, clean).replaceAll('\\', '/')}`); continue }
          throw new Error('The plugin build included a file outside its package and public SDK.')
        }
        for (const worker of workers) {
          const assets = Object.values(bundle).filter(item => item.type === 'asset' && Buffer.from(item.source).equals(worker.bytes))
          const loaders = Object.values(bundle).filter(item => item.type === 'chunk' &&
            Object.keys(item.modules).some(id => path.resolve(id.split('?')[0]) === worker.loader))
          if (assets.length !== 1 || !assets[0].fileName.endsWith('.js') || !loaders.length) {
            throw new Error('Every declared worker must be emitted as a separate JavaScript asset with its loader; use ?url&no-inline.')
          }
          frontendWorkers.push({ entry: assets[0].fileName, loaders: loaders.map(item => item.fileName).sort() })
        }
      },
    }],
    build: {
      outDir: out, emptyOutDir: false, sourcemap: false,
      lib: { entry: entryPath, formats: ['es'], fileName: 'index' },
      rollupOptions: { output: { entryFileNames: 'index.js', chunkFileNames: 'chunks/[name]-[hash].js', assetFileNames: '[name][extname]' } },
    },
  })
  await mkdir(out, { recursive: true })
  await writeFile(path.join(out, 'styles.css'), styles.css)
  const modules = [...new Set(moduleNames)].sort()
  const vendors = new Set(modules.filter(name => name.startsWith('node_modules/')).map(name => {
    const parts = name.slice('node_modules/'.length).split('/')
    return parts[0].startsWith('@') ? parts.slice(0, 2).join('/') : parts[0]
  }))
  const notices = []
  for (const vendor of [...vendors].sort()) {
    const folder = await realpath(path.join(root, 'node_modules', vendor))
    if (!inside(folder, root)) throw new Error('Dependency notices must stay inside the product build.')
    const metadata = JSON.parse(await readFile(path.join(folder, 'package.json'), 'utf8'))
    const licenses = (await readdir(folder)).filter(name => /^(license|licence|copying|notice)([._-].*)?$/i.test(name))
    if (!licenses.length) throw new Error(`Include the license notices for bundled dependency ${vendor}.`)
    notices.push(`${metadata.name} ${metadata.version} (${metadata.license || 'see license below'})`)
    for (const filename of licenses.sort()) notices.push(await readFile(path.join(folder, filename), 'utf8'))
  }
  notices.push(`LDS frontend SDK ${SDK_PACKAGE.version}`, await readFile(path.join(SDK_ROOT, 'LICENSE'), 'utf8'))
  await writeFile(path.join(out, 'THIRD-PARTY-NOTICES.txt'), notices.join('\n\n') + '\n')
  await writeFile(path.join(out, 'build-report.json'), JSON.stringify({ sdk: SDK_PACKAGE.version, id: manifest.id, version: manifest.version, modules, frontend_workers: frontendWorkers }, null, 2) + '\n')
  return { result, modules, frontend_workers: frontendWorkers }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2)
  const value = (name) => args[args.indexOf(name) + 1]
  if (!args.includes('--plugin') || !args.includes('--out')) throw new Error('Usage: lds-plugin-build --plugin <package> --out <ui-directory>')
  await buildPlugin({ plugin: value('--plugin'), outDir: value('--out') })
}
