import { useState } from 'react'
import { imageVersionQuery } from './bankEdits.js'

/** Both frames use the same space, so a larger upscale stays comparable. */
export default function BankEditComparison({ bankId, image }) {
  const [failed, setFailed] = useState(false)
  const url = `/api/bank/${bankId}/file/${image.id}${imageVersionQuery(image)}`
  const before = `${url}${url.includes('?') ? '&' : '?'}previous=1`
  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-2">
      {failed && <p role="alert" className="text-center text-sm text-amber-200">
        The previous version is unavailable. Its file may have changed or been removed.
      </p>}
      <div className="grid min-h-0 flex-1 grid-cols-2 gap-3">
        {[['Before last edit', before], ['Current version', url]].map(([label, src]) => (
          <figure key={label} className="flex min-h-0 min-w-0 flex-col gap-2">
            <figcaption className="text-center text-xs text-white/80">{label}</figcaption>
            <img src={src} alt={`${label}: ${image.name || 'Bank image'}`}
              onError={() => setFailed(true)}
              className="min-h-0 w-full flex-1 select-none object-contain" />
          </figure>
        ))}
      </div>
    </div>
  )
}
