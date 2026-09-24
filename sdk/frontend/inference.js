import { runtime } from './runtime.js'
// Shared host interaction and presentation contract, version 1.5.
// Extracted from LDS under PolyForm-Noncommercial-1.0.0.

export const SUPERSEDED_ANSWER_NOTICE =
  'The ✨ answer to an earlier click arrived after you moved on — set aside, nothing was written.';

export function keepAnswer(run, tell) {
  if (!run?.current || run.current()) return true;
  if (tell && run.mounted()) tell();
  return false;
}

export function canvasImproveRefusal(img) {
  if (!img || !Number.isInteger(Number(img.id))) {
    // A picture the board holds only as a URL — the lane's reference face, a
    // pill's preview. There is no row to improve, and no id to send.
    return 'This picture has no library entry to improve.'
  }
  return null
}

export const canImproveCanvasImage = (img) => canvasImproveRefusal(img) === null
export function useOllamaFence(...args) { return runtime().inference.useOllamaFence(...args) }
export function useCanvasImageImprove(...args) { return runtime().inference.useCanvasImageImprove(...args) }
export function useRestoreImproveSettings(...args) { return runtime().inference.useRestoreImproveSettings(...args) }
export function OllamaFenceNotice(props) {
  const host = runtime()
  return host.React.createElement(host.inference.OllamaFenceNotice, props)
}

export function improveEngine(...args) { return runtime().inference.improveEngine(...args) }
export function availableImproveEngines(...args) { return runtime().inference.availableImproveEngines(...args) }
export function improvementAvailable() { return runtime().inference.improvementAvailable() }
