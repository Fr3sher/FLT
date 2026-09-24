import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')

test('the button only exists when a host offers the URL, and says it is working', () => {
  const src = read('../frontend/SideBySideVideo.jsx')
  assert.match(src, /\{exportHref && \(/)      // no prop, no button
  assert.match(src, /exporting \? 'Building…' : '⬇ Export'/)
  assert.match(src, /disabled=\{exporting\}/)  // one click, not five
  assert.match(src, /role="alert"/)            // the failure is on screen
  // Finger-sized below lg, like every other control in this layer.
  assert.ok(src.includes('min-h-10 rounded-md border border-border px-2 py-1 text-xs'))
})
