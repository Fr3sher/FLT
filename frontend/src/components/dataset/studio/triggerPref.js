// Trigger word is ONE browser preference shared by Test Studio, Compare and Canvas launch
// surfaces; unchecking applies everywhere. Default is INJECT, preserving existing behavior. Write
// storage only for unchecked state so defaults leave no trace. Keep this module pure: panels do
// not touch storage themselves, and the prompt-batch contract forbids persistence in
// RunSetupPanel.
const KEY = 'studioInjectTrigger';

export function readInjectTrigger() {
  try { return window.localStorage.getItem(KEY) !== '0'; } catch { return true; }
}

export function writeInjectTrigger(v) {
  try {
    if (v) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, '0');
  } catch { /* Storage unavailable: keep a session-only preference. */ }
}
