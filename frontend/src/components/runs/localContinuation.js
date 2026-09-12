// The main Canvas already addresses an explicit save instead of the latest
// file of a whole lane. The public plugin host also checks its saved-run owner.
import { canvasContinueRequest } from '../../utils/canvasContinue.js'
import { isFullTransformerRun } from '../../utils/trainingMode.js'

export const CLOUD_LOCAL_UNAVAILABLE = 'Local continuation of cloud checkpoints is not supported.'

export function explicitRunContinuation(run, payload) {
  if (!run || !payload || !['local', 'cloud'].includes(run.source)) return null
  if (run.source === 'cloud' && payload.lane !== 'cloud') return null
  if (payload.lane != null && !['local', 'cloud'].includes(payload.lane)) return null
  const candidates = Array.isArray(run.resume_checkpoints) && run.resume_checkpoints.length
    ? run.resume_checkpoints.map(checkpoint => checkpoint?.step)
    : (Array.isArray(run.resume_steps) ? run.resume_steps : [])
  const steps = candidates.filter(step => Number.isInteger(step) && step > 0)
  const fromStep = payload.fromStep ?? (steps.length ? Math.max(...steps) : null)
  if (!steps.includes(fromStep)) return null
  if (run.source === 'local') {
    if (!Number.isInteger(run.record_id) || run.record_id <= 0) return null
    return { ...payload, fromStep, expectedRecordId: run.record_id }
  }
  return { ...payload, fromStep }
}

export function localContinuationAvailability(run, { aitoolkitValid, localActive } = {}) {
  if (!run) return null
  const reason = run.source !== 'local' ? CLOUD_LOCAL_UNAVAILABLE
    : isFullTransformerRun(run) ? 'Full-model training is unavailable on the local trainer.'
      : run.train_type === 'video' || run.dataset_table === 'video_dataset'
        ? 'Continue this video run from its video dataset.'
        : aitoolkitValid !== true ? 'Local training needs a verified ai-toolkit installation.'
          : run.dataset_id == null ? 'This run has no dataset to continue.'
            : localActive ? 'A training is already running on this machine.' : null
  return reason ? { available: false, reason } : { available: true }
}

export function localContinuationRequest(run, payload) {
  if (!payload) return null
  const selected = explicitRunContinuation(run, { ...payload, lane: 'local' })
  if (!selected || run.source !== 'local' || run.dataset_id == null) return null
  const request = canvasContinueRequest(run, selected, { masked: run.masked })
  if (!request) return null
  request.body.expected_record_id = selected.expectedRecordId
  return request
}
