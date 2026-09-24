// The lazy component of a plugin ROUTE, created once per route and kept.
//
// Why a cache and not a `useMemo` in the route component: a component created
// inside a render that then SUSPENDS never commits, so React throws that render
// away and retries — a `useMemo` in it runs again, makes a new `lazy()`, which
// starts a new import and suspends again. The page spins forever with every
// request finished and nothing in the console. Measured on `#/video-bank`, the
// first route a plugin ever contributed (2026-09-05): the API answered in 3 ms
// and the spinner stayed 40 s. `PluginPanel` had the same shape and the same
// cache from the start (`lazyPanel`); routes get theirs here, wrapped in
// `lazyPage` so a plugin's chunk keeps the one reload after an update that the
// core's pages have.
import { lazyPage } from '../utils/lazyPage.js'

const cache = new Map()

export function lazyRoute(key, importer) {
  if (!cache.has(key)) cache.set(key, lazyPage(importer))
  return cache.get(key)
}

/** Test seam: forget every route (a test registers plugins of its own). */
export function resetLazyRoutes() {
  cache.clear()
}
