/*
 * Show flagged pages and their target zones INSIDE the test launch dialog, as requested, so
 * results can be judged without leaving it. One component serves both surfaces under the parity
 * rule: Bank uses its preview endpoint; Dataset uses flagged payload rows. Each tile opens the
 * full-size page because a thumbnail shows zones, but judging borderline boxes such as clipped
 * bubble outlines requires full pixels.
 */
import { galleryHeadline, galleryZones, zoneStyle } from './textZonesGallery.js'

export default function TextZonesGallery({
  items = [], total = 0, live = false, emptyLine = null, reviewHint = '',
}) {
  if (!items.length) {
    if (live) {
      return (
        <p className="m-0 text-[11px] leading-snug text-content-subtle">
          Scanning — nothing flagged yet. Pages appear here as they are flagged.
        </p>
      )
    }
    return emptyLine
      ? <p className="m-0 text-[11px] leading-snug text-content-subtle">{emptyLine}</p>
      : null
  }
  return (
    <div className="space-y-1">
      <p className="m-0 text-[11px] leading-snug text-content-subtle">
        <span className="font-medium text-content">Flagged pages and their zones</span>
        {galleryHeadline(items.length, total)}
        {reviewHint ? `. ${reviewHint}` : '.'}
      </p>
      <ul className="m-0 flex list-none gap-2 overflow-x-auto p-0 pb-1">
        {items.map((it) => (
          <li key={it.id} className="shrink-0">
            <a href={it.href || it.src} target="_blank" rel="noreferrer"
              title="Open the full-size page in a new tab"
              className="relative block overflow-hidden rounded-md border border-border">
              <img src={it.src} alt={it.alt || `Page ${it.id} with its zones`}
                loading="lazy" className="h-48 w-auto object-contain" />
              {galleryZones(it.regions).map((zone, i) => (
                <span key={i} aria-hidden
                  className="absolute border border-amber-400 bg-amber-400/20"
                  style={zoneStyle(zone)} />
              ))}
            </a>
            <p className="m-0 mt-0.5 text-center text-[10px] text-content-subtle">#{it.id}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
