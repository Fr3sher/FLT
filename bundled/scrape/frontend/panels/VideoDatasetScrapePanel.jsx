import { useState } from 'react'
import { postJson } from '@lds/plugin-sdk'
import ConceptSourcesPanel from './ConceptSourcesPanel.jsx'

export default function VideoDatasetScrapePanel({ datasetId, busy, sliceLong, onDone }) {
  const [error, setError] = useState('')
  const handleImport = async (items) => {
    setError('')
    try {
      const result = await postJson(`/api/video-dataset/${datasetId}/scrape-import`, {
        items, slice_long: sliceLong === true,
      })
      await onDone?.()
      return result
    } catch (e) { setError(e.message); return { ok: false } }
  }
  return <>
    <p className="text-xs text-content-subtle">Select the videos to import, up to 200 MB each.</p>
    {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
    <ConceptSourcesPanel destination="video-dataset" stateKey={`video-dataset:${datasetId}`}
      datasetId={datasetId} busy={busy} onImport={handleImport} />
  </>
}
