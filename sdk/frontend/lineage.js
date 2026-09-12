// Stable run lineage presentation; actions remain in each owning product.
import { runtime } from './runtime.js'
export const CARD_W = 264
export const POPOVER_W = 210
function control(name, props) {
  const host = runtime()
  return host.React.createElement(host.lineage[name], props)
}
export function GraphCard(props) { return control('GraphCard', props) }
export function CheckpointPill(props) { return control('CheckpointPill', props) }
export function LineageEdgeDefs(props) { return control('LineageEdgeDefs', props) }
export function LineageEdges(props) { return control('LineageEdges', props) }
export function buildLineageGraph(...args) { return runtime().lineage.buildLineageGraph(...args) }
export function clampPopoverToViewport(...args) { return runtime().lineage.clampPopoverToViewport(...args) }
export function popoverHeight(...args) { return runtime().lineage.popoverHeight(...args) }
