import { contributions } from './registry.js'
import { POPOVER_H } from '../components/dataset/checkpointPopover.js'
export { clampPopoverToViewport, POPOVER_W } from '../components/dataset/checkpointPopover.js'

// Retain main's full reservation until its existing rows transfer atomically.
// Added plugin rows get their own space on the surface that hosts them.
export function popoverHeight(surface) {
  return POPOVER_H + 31 * contributions('checkpoint.action', surface).length
}
