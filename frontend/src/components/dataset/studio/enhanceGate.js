// react-frontend/src/components/dataset/studio/enhanceGate.js
/**
 * Decide whether Enhance is available and explain WHY when blocked. Extracted from JSX for node
 * --test. Without Ollama, disable with the exact tooltip reason rather than sending a request that
 * fails silently. The three states come from existing /api/capabilities caps.ollama used by Bank
 * and Settings.
 */

/**
 * Return an English blocking reason or null when Enhance is available. customModel is the explicit
 * settings choice, empty for default. When set, a missing default model does not block because it
 * is unused; the server validates the selected model and names it in any 409.
 */
export function enhanceBlocker(ollama, { capsLoading = false, customModel = '' } = {}) {
  if (capsLoading) return 'Checking local tools…';
  const o = ollama || {};
  // LM Studio answers a different ladder: it cannot be started from here, and
  // "ready" means a model is LOADED, not pulled. Told to install Ollama, a user
  // who deliberately chose the other provider is being sent to the wrong product
  // — and the button stayed disabled while the backend answered 200.
  if (o.provider === 'lmstudio') {
    if (!o.reachable) {
      // Installed = its CLI is on disk, so LDS can start the server itself. Sending
      // someone to another application's menu when a button here would do it is the
      // same dead end this file exists to remove.
      return o.installed
        ? 'LM Studio is not running — start it from Settings › Local tools.'
        : 'LM Studio is not answering — open it, go to Developer and press Start Server.';
    }
    if (!customModel && !o.vision_model_ready) {
      return 'LM Studio has no usable model loaded — load a vision model in its Developer tab.';
    }
    return null;
  }
  if (!o.installed && !o.reachable) {
    return 'Enhance needs Ollama — install it from Settings › Local tools.';
  }
  if (!o.reachable) {
    return 'Ollama is installed but not running — start it from Settings › Local tools.';
  }
  if (!customModel && !o.vision_model_ready) {
    return `Ollama model "${o.vision_model || 'unset'}" is not downloaded yet `
      + '— pull it from Settings › Local tools.';
  }
  return null;
}
