import { existsSync, readdirSync, realpathSync, statSync } from 'node:fs'
import path from 'node:path'
import { parse as parseHtml } from 'parse5'
import postcss from 'postcss'
import valueParser from 'postcss-value-parser'
import { transformWithEsbuild } from 'vite'

/** Only an explicit development opt-in may compile private product sources. */
export function resolvePluginBuildMode(env = {}, environment = process.env) {
  return (environment.LDS_PLUGIN_BUILD_MODE || env.LDS_PLUGIN_BUILD_MODE) === 'bundled'
    ? 'bundled' : 'store'
}

function isPrivateProductModule(id) {
  if (typeof id !== 'string') return false
  const clean = id.replace(/^\0/, '').split(/[?#]/, 1)[0]
  const isBundledPath = value => /(?:^|\/)bundled(?:\/|$)/i.test(value.replaceAll('\\', '/'))
  if (isBundledPath(clean)) return true
  if (!path.isAbsolute(clean)) return false
  try {
    // A symlink with a public-looking name still reads the private source.
    return isBundledPath(realpathSync.native(clean))
  } catch {
    return false // Virtual/generated IDs may not have a file on disk.
  }
}

/** Guard actual Vite inputs, including CSS dependencies and transformed IDs. */
export function privatePluginBuild({ distribution }) {
  const store = distribution !== 'bundled'
  let config
  let buildContext
  function check(context, id) {
    if (store && isPrivateProductModule(id)) {
      context.error('Private plugin source cannot enter a Store build; use the public SDK or a plugin contribution.')
    }
  }

  // Vite reads and inlines new URL()/HTML assets without load(), module IDs or
  // watch files. assetsInlineLimit is not a provenance hook: ?inline bypasses
  // it, and new URL() processing even swallows its exceptions. Check structured
  // source references BEFORE Vite reads them, using its resolver for aliases.
  async function checkUrl(context, value, importer) {
    if (typeof value !== 'string') return
    const url = value.trim()
    if (!url || (!path.isAbsolute(url.split(/[?#]/, 1)[0]) && /^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(url))) return
    let decoded = url
    try { decoded = decodeURIComponent(url) } catch { /* Vite diagnoses malformed URLs. */ }
    check(context, decoded)
    const clean = decoded.split(/[?#]/, 1)[0]
    const importerFile = importer.split(/[?#]/, 1)[0]
    if (clean.startsWith('/')) {
      check(context, path.join(config.root, clean))
      if (config.publicDir) check(context, path.join(config.publicDir, clean))
    } else {
      check(context, path.resolve(path.dirname(importerFile), clean))
    }
    const resolved = await context.resolve(decoded, importerFile, { skipSelf: true })
    if (resolved) check(context, resolved.id)
  }

  async function checkCss(context, code, importer) {
    const references = []
    const sheet = postcss.parse(code, { from: importer })
    function collect(value, importRule = false) {
      const parsed = valueParser(value)
      parsed.walk((node, _index, siblings) => {
        if (node.type === 'function' && node.value.toLowerCase() === 'url') {
          references.push(valueParser.stringify(node.nodes).replace(/^(['"])(.*)\1$/, '$2'))
          return false
        }
        if (node.type === 'function' && /^(?:-webkit-)?image-set$/i.test(node.value)) {
          for (const child of node.nodes) if (child.type === 'string') references.push(child.value)
        }
        if (importRule && node.type === 'string' && siblings === parsed.nodes) references.push(node.value)
      })
    }
    sheet.walkDecls(declaration => collect(declaration.value))
    sheet.walkAtRules('import', rule => collect(rule.params, true))
    for (const url of references) await checkUrl(context, url, importer)
  }

  async function checkJs(context, code, importer) {
    if (!code.includes('URL') || !code.includes('import.meta')) return
    let ast
    try { ast = context.parse(code) } catch {
      // The pre-hook also sees JSX/TS before Vite compiles it. Parse an esbuild
      // projection without replacing the source or relying on string regexes.
      const transformed = await transformWithEsbuild(code, importer, { loader: /\.tsx?(?:\?|$)/.test(importer) ? 'tsx' : 'jsx' })
      ast = context.parse(transformed.code)
    }
    const references = []
    function visit(node) {
      if (!node || typeof node !== 'object') return
      if (node.type === 'NewExpression' && node.callee?.name === 'URL') {
        const [url, base] = node.arguments
        if (base?.type === 'MemberExpression' && base.property?.name === 'url' && base.object?.type === 'MetaProperty') {
          if (url?.type === 'Literal') references.push(url.value)
          if (url?.type === 'TemplateLiteral' && url.expressions.length === 0) references.push(url.quasis[0].value.cooked)
        }
      }
      for (const child of Object.values(node)) {
        if (Array.isArray(child)) child.forEach(visit)
        else if (child && typeof child === 'object') visit(child)
      }
    }
    visit(ast)
    for (const url of references) await checkUrl(context, url, importer)
  }

  async function checkHtml(context, html, importer) {
    const nodes = [parseHtml(html)]
    while (nodes.length) {
      const node = nodes.pop()
      nodes.push(...(node.childNodes || []))
      if (node.content) nodes.push(node.content)
      for (const attribute of node.attrs || []) {
        if (['src', 'href', 'poster', 'data'].includes(attribute.name)) await checkUrl(context, attribute.value, importer)
        if (node.nodeName === 'meta' && attribute.name === 'content') await checkUrl(context, attribute.value, importer)
        if (['srcset', 'imagesrcset'].includes(attribute.name)) {
          // HTML parsing has already decoded entities; each candidate URL is
          // its first whitespace-delimited token (data: candidates are skipped).
          for (const candidate of attribute.value.split(',')) await checkUrl(context, candidate.trim().split(/\s+/, 1)[0], importer)
        }
        if (attribute.name === 'style') await checkCss(context, `.inline{${attribute.value}}`, importer)
      }
      const text = (node.childNodes || []).filter(child => child.nodeName === '#text').map(child => child.value).join('')
      if (node.nodeName === 'style') await checkCss(context, text, importer)
      if (node.nodeName === 'script' && node.attrs?.some(attr => attr.name === 'type' && attr.value === 'module')) await checkJs(context, text, importer)
    }
  }

  function checkPublicDirectory(context, directory, seen = new Set()) {
    if (!directory || !existsSync(directory)) return
    check(context, directory)
    const real = realpathSync.native(directory)
    if (seen.has(real)) return
    seen.add(real)
    for (const entry of readdirSync(directory)) {
      const file = path.join(directory, entry)
      check(context, file)
      if (statSync(file).isDirectory()) checkPublicDirectory(context, file, seen)
    }
  }
  return {
    name: 'lds-private-plugin-build-boundary',
    enforce: 'pre',
    configResolved(resolved) { config = resolved },
    buildStart() {
      buildContext = this
      if (store) checkPublicDirectory(this, config.publicDir)
    },
    load(id) {
      check(this, id)
      return null
    },
    async transform(code, id) {
      check(this, id)
      if (store) {
        const clean = id.split(/[?#]/, 1)[0]
        if (clean.endsWith('.css')) await checkCss(this, code, id)
        else if (!clean.endsWith('.html')) await checkJs(this, code, id)
      }
      return null
    },
    transformIndexHtml: {
      order: 'pre',
      async handler(html, context) {
        if (store) await checkHtml(buildContext, html, context.filename)
      },
    },
    generateBundle: {
      order: 'post',
      handler(_options, bundle) {
        // Run after ordinary asset emitters, before Rollup writes any output.
        // CSS @imports may be watched dependencies rather than Rollup modules.
        for (const id of this.getModuleIds()) check(this, id)
        for (const id of this.getWatchFiles()) check(this, id)
        for (const asset of Object.values(bundle)) {
          if (asset.type !== 'asset') continue
          for (const id of asset.originalFileNames || []) check(this, path.resolve(config.root, id))
        }
      },
    },
  }
}
