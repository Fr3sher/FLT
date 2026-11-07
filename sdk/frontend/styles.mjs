import selectorParser from 'postcss-selector-parser'

/** Namespace utility classes, including group/peer selectors and media rules.
 * A late-loaded `.flex` must never override the host's `.md:hidden`.
 * React maps the resolved className string, so dynamic class expressions and
 * portal content receive the same namespace without rewriting product sources.
 */
export function namespaceUtilities(root, pluginId) {
  if (!/^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?$/.test(pluginId)) throw new Error('Invalid plugin style identity.')
  const prefix = `lds-${pluginId.replaceAll('.', '-')}-`
  const classes = new Set()
  root.walkRules(rule => {
    rule.selector = selectorParser(selectors => {
      selectors.walkClasses(node => {
        classes.add(node.value)
        node.value = prefix + node.value
      })
    }).processSync(rule.selector)
  })
  return { css: root.toString(), classes: [...classes].sort(), prefix }
}

export function styleRuntimeSource({ classes, prefix }) {
  return `const classes=new Set(${JSON.stringify(classes)});\n`
    + `export function scopeProps(props) {\n`
    + ` if (!props || typeof props.className !== 'string') return props;\n`
    + ` return {...props,className:props.className.split(/\\s+/).map(name=>classes.has(name)?${JSON.stringify(prefix)}+name:name).join(' ')};\n}\n`
}
