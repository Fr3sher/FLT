/** 🎬 Video bank — the URLs, built in one place.
 *
 * Every path this lane talks to is assembled here rather than interpolated at
 * the call site, for one reason that has already cost this project a wave: the
 * clip list endpoint answers TWO different shapes from the same route
 * (`{clips,total}` normally, `{ids,total}` with `ids_only=1`), and a query
 * string built by hand in three components drifts into a fourth shape nobody
 * tested.
 *
 * PURE STRINGS, no fetch: `node --test` imports this file directly.
 */

/** The JPEG the grid shows. 404 until the thumbnails pass has run — that is an
 * ordinary state, not an error, and the grid draws a placeholder on it. */
export function videoClipThumbUrl(bankId, clipId) {
  return `/api/video-bank/${bankId}/clip/${clipId}/thumb`
}

/** The SOURCE file's bytes — the `base` every media fragment is built on.
 *
 * Deliberately per-SOURCE and not per-clip: a bank writes no clip files, so
 * there is nothing else to point at. The lightbox appends `#t=start,end` (see
 * videoClipFragment.clipFragmentSrc) and the browser range-requests only that
 * span out of what can be a multi-gigabyte rush. */
export function videoSourceMediaUrl(bankId, sourceId) {
  return `/api/video-bank/${bankId}/source/${sourceId}/media`
}

/** The workspace payload AND the 2 s poll. `refresh` re-walks the source folder
 * server-side; send it when the bank is OPENED, never on the poll — it costs a
 * directory walk of the whole tree every two seconds otherwise. */
export function videoBankUrl(bankId, { refresh = false } = {}) {
  return `/api/video-bank/${bankId}${refresh ? '?refresh=1' : ''}`
}

/** One page of the clip gallery, or the whole filter as bare ids.
 *
 * A falsy `status` means "every status" and MUST be left out of the query: the
 * server filters on `status in TRIAGE_STATUSES`, so `status=` or `status=all`
 * would silently return everything while the UI believed it had filtered. Same
 * for `source_id` — the server reads a bare int and treats 0 as absent. */
export function videoClipsUrl(bankId, {
  status = null, sourceId = null, offset = 0, limit = 200, idsOnly = false,
} = {}) {
  const q = new URLSearchParams()
  if (status && status !== 'all') q.set('status', status)
  if (sourceId) q.set('source_id', String(sourceId))
  if (idsOnly) {
    // offset/limit are meaningless alongside ids_only (the server answers the
    // WHOLE filter) — sending them reads like a paged answer that it is not.
    q.set('ids_only', '1')
  } else {
    if (offset) q.set('offset', String(offset))
    q.set('limit', String(limit))
  }
  const qs = q.toString()
  return `/api/video-bank/${bankId}/clips${qs ? `?${qs}` : ''}`
}

/** Pass endpoints, so the four buttons cannot disagree about their own names. */
export function videoPassUrl(bankId, pass) {
  return `/api/video-bank/${bankId}/${pass}`
}

/** A video dataset's own page. Kept here so the library card and the promote
 * dialog's "open it" link build the same address. */
export function videoDatasetUrl(datasetId) {
  return `/api/video-dataset/${datasetId}`
}
