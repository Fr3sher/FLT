/** The Bank's interactive surfaces, read off the SOURCE TEXT.
 *
 * This exists to make "no button was lost" checkable instead of promised. The
 * redesign moves JSX between files wholesale; a test that asserted a label in a
 * given FILE would fail on every move and teach us to weaken it. So the
 * inventory is checked against the CONCATENATED Bank tree: moving a button
 * keeps it green, deleting one turns it red.
 *
 * Two traps this had to survive, both of which produced a guard that looked
 * green while covering nothing:
 *
 *  1. Matching only buttons whose body is plain text. Almost every interesting
 *     button here carries a conditional suffix or wraps its label in a span,
 *     so that shape skipped exactly the buttons worth protecting.
 *  2. Ending the opening tag at the first ">". Attributes hold arrow functions
 *     (onClick={() => …}), so the "body" started mid-attribute and the
 *     inventory filled up with className fragments.
 *
 * Hence the hand-rolled scan below: it tracks quotes and brace depth to find
 * where the opening tag really ends.
 *
 * A label that is entirely computed still yields nothing, and that is correct:
 * no frozen string could match a value built at runtime. Those stay covered by
 * the unit tests that own the helper building them. */

const ATTRIBUTE = /\b(?:aria-label|title)="([^"{}]+)"/g

/* Cut on a SENTINEL, never on whitespace. Splitting on spaces would turn one
   label into a list of separate words, and an inventory of words matches
   anything — the guard would stay green on a Bank that had lost the button. */
const CUT = '\u0000'

/** Index just past the ">" that closes the JSX opening tag starting at `from`,
 *  or -1. Skips over quoted strings and {…} expressions, which is what makes
 *  an attribute like onClick={() => setOpen(true)} stop confusing the scan. */
function endOfOpeningTag(source, from) {
  let depth = 0
  let quote = null
  for (let i = from; i < source.length; i += 1) {
    const c = source[i]
    if (quote) {
      if (c === quote) quote = null
      continue
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue }
    if (c === '{') { depth += 1; continue }
    if (c === '}') { depth -= 1; continue }
    if (c === '>' && depth === 0) return i + 1
  }
  return -1
}

/* Leftovers of the syntax around a label, not the label: the ")" of a ternary,
   the "}" of an expression, a block comment that lived inside the body. Note
   what is NOT in here — "✕", "→", "▶" are ASCII-free symbols and they are real
   button labels, so the rule is "only ASCII punctuation", not "no letters". */
const SYNTAX_ONLY = /^[\s(){}[\]/#;:,.+\-=|&?!*<>'"`]+$/
const CODE_COMMENT = /\/\*|\*\//

/** Literal text runs inside a JSX element body: drop the expressions and the
 *  nested tags, keep what a user would actually read. */
function literalRuns(body) {
  return body
    .replace(/\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, CUT)
    .replace(/<[^>]*>/g, CUT)
    .split(CUT)
    .map((run) => run.replace(/\s+/g, ' ').trim())
    .filter((run) => run && !SYNTAX_ONLY.test(run) && !CODE_COMMENT.test(run))
}

function buttonBodies(source) {
  const bodies = []
  let at = 0
  for (;;) {
    const open = source.indexOf('<button', at)
    if (open === -1) return bodies
    const bodyStart = endOfOpeningTag(source, open + 7)
    if (bodyStart === -1) return bodies
    // A self-closing <button … /> has no body worth reading.
    if (source[bodyStart - 2] === '/') { at = bodyStart; continue }
    const close = source.indexOf('</button>', bodyStart)
    if (close === -1) return bodies
    bodies.push(source.slice(bodyStart, close))
    at = close + 9
  }
}

export function surfaceStrings(source) {
  const found = []
  for (const body of buttonBodies(source)) found.push(...literalRuns(body))
  for (const [, text] of source.matchAll(ATTRIBUTE)) {
    const label = text.replace(/\s+/g, ' ').trim()
    if (label) found.push(label)
  }
  return found
}
