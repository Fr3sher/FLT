// The main Canvas already addresses an explicit save instead of the latest
// file of a whole lane. The public plugin host also checks its saved-run owner.
import { canvasContinueRequest } from '../../utils/canvasContinue.js'
import { isFullTransformerRun } from '../../utils/trainingMode.js'

export const CLOUD_LOCAL_UNAVAILABLE = 'Local continuation of cloud checkpoints is not supported.'

export function explicitRunContinuation(run, payload) {
  if (!run || !payload || !['local', 'cloud'].includes(run.source)) return null
  if (payload.lane != null && !['local', 'cloud'].includes(payload.lane)) return null
  const candidates = Array.isArray(run.resume_checkpoints) && run.resume_checkpoints.length
    ? run.resume_checkpoints.filter(checkpoint => checkpoint?.present !== false).map(checkpoint => checkpoint?.step)
    : (Array.isArray(run.resume_steps) ? run.resume_steps : [])
  const steps = candidates.filter(step => Number.isInteger(step) && step > 0)
  const fromStep = payload.fromStep ?? (steps.length ? Math.max(...steps) : null)
  if (!steps.includes(fromStep)) return null
  if (run.source === 'local' || payload.lane !== 'cloud') {
    if (!Number.isInteger(run.record_id) || run.record_id <= 0) return null
    if (run.source === 'cloud' && (!Number.isInteger(run.run_id) || run.run_id <= 0
      || !Number.isInteger(run.dataset_id) || run.dataset_id <= 0
      || isFullTransformerRun(run) || run.train_type === 'video' || run.dataset_table === 'video_dataset'
      || (payload.resumeMode && payload.resumeMode !== 'weights_only'))) return null
    return { ...payload, fromStep, expectedRecordId: run.record_id }
  }
  return { ...payload, fromStep }
}

export function localContinuationAvailability(run, { aitoolkitValid, localActive } = {}) {
  if (!run) return null
  const reason = !['local', 'cloud'].includes(run.source) ? CLOUD_LOCAL_UNAVAILABLE
    : isFullTransformerRun(run) ? 'Full-model training is unavailable on the local trainer.'
      : run.train_type === 'video' || run.dataset_table === 'video_dataset'
        ? 'Continue this video run from its video dataset.'
        : aitoolkitValid !== true ? 'Local training needs a verified ai-toolkit installation.'
          : run.dataset_id == null ? 'This run has no dataset to continue.'
            : localActive ? 'A training is already running on this machine.'
              : !explicitRunContinuation(run, { lane: 'local' })
                ? 'This checkpoint’s run identity or saved file is unavailable. Refresh its checkpoints before continuing.' : null
  return reason ? { available: false, reason } : { available: true }
}

export function localContinuationRequest(run, payload) {
  if (!payload) return null
  const selected = explicitRunContinuation(run, { ...payload, lane: 'local' })
  if (!selected || run.dataset_id == null) return null
  const request = canvasContinueRequest(run, selected, { masked: run.masked })
  if (!request) return null
  request.body.expected_record_id = selected.expectedRecordId
  return request
}

// Map a lineage checkpoint to the same run-addressed continuation contract.
export function continuationFromNode(node, rows = []) {
  if (!node || !['local', 'cloud'].includes(node.source)) return null
  const row = rows.find(candidate => candidate.source === node.source
    && (node.source === 'cloud' ? candidate.run_id === node.run_id : candidate.record_id === node.record_id))
  const checkpoints = Array.isArray(node.checkpoints) ? node.checkpoints : []
  return { ...node, ...row, resume_steps: checkpoints.map(checkpoint => checkpoint.step), resume_checkpoints: checkpoints }
}
