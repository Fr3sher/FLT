// Shared download transport validates HTTP results before offering a file.
import { runtime } from './runtime.js'
export function isAbort(...args) { return runtime().files.isAbort(...args) }
export function saveUrlAsFile(...args) { return runtime().files.saveUrlAsFile(...args) }
