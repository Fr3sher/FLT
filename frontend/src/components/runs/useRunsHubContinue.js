import { useRef, useState } from 'react'
import { useCapabilities } from '../../context/CapabilitiesContext.jsx'
import { useToast } from '../common/Toast.jsx'
import { postJson } from '../../api/fetchClient.js'
import { postWithConfirmations } from '../../utils/trainingRefusals.js'
import { continueAttemptOutcome } from '../../utils/continueOutcome.js'
import { isFullTransformerRun } from '../../utils/trainingMode.js'
import { isTrainingRecipeReplayBlocked } from '../../utils/trainingRuns.js'
import { explicitRunContinuation, localContinuationAvailability, localContinuationRequest } from './localContinuation.js'

// Public main's Continue dialog/confirmation/recipe contracts. The optional
// cloud capability owns its own availability, forecast and submit transport.
export default function useRunsHubContinue({ data, poll, cloud = null }) {
  const { caps } = useCapabilities()
  const toast = useToast()
  const [target, setTarget] = useState(null)
  const targetRef = useRef(null)
  const [initialStep, setInitialStep] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)
  const [transportPlan, setTransportPlan] = useState(null)
  const local = localContinuationAvailability(target, { aitoolkitValid: caps?.aitoolkit?.valid, localActive: data?.local_active })
  const remote = target && typeof cloud?.submit === 'function' ? cloud?.availability?.(target, { data, caps }) : null
  const lanes = target ? { local, cloud: remote || {
    available: false, reason: 'Cloud training is disabled in this install.',
  } } : null
  const canContinueRun = run => run?.source === 'local'
    || !!explicitRunContinuation(run, { lane: 'local' }) || typeof cloud?.submit === 'function'

  const open = (run, step = null) => {
    if (!run || busyRef.current || !canContinueRun(run)) return
    if (isTrainingRecipeReplayBlocked(run)) {
      toast.error('This checkpoint uses an incompatible training recipe. Start a fresh validated run.')
      return
    }
    targetRef.current = run
    setTarget(run)
    setInitialStep(step)
    setError(null)
    setTransportPlan(null)
    if (typeof cloud?.plan === 'function' && isFullTransformerRun(run)) {
      Promise.resolve().then(() => cloud.plan(run)).then(plan => {
        if (targetRef.current === run) setTransportPlan(plan)
      }).catch(() => { /* The optional forecast does not replace launch validation. */ })
    }
  }
  const continueFromCheckpoint = (node, pill) => {
    if (!node) return
    const row = [...(data?.actives || []), ...(data?.recent || [])].find(run =>
      run.source === node.source && (node.source === 'cloud' ? run.run_id === node.run_id : run.record_id === node.record_id))
    const checkpoints = node.checkpoints || []
    open({ ...node, ...row, resume_checkpoints: checkpoints, resume_steps: checkpoints.map(item => item.step) }, pill?.step ?? null)
  }
  const submitContinue = async payload => {
    if (busyRef.current) return
    if (!payload) { targetRef.current = null; setTarget(null); return }
    const run = targetRef.current
    const lane = payload.lane || (run?.source === 'cloud' ? 'cloud' : 'local')
    const selected = explicitRunContinuation(run, { ...payload, lane })
    if (!selected || lanes?.[lane]?.available !== true) {
      setError(lanes?.[lane]?.reason || 'This saved checkpoint or continuation lane is unavailable.')
      return
    }
    busyRef.current = true
    setBusy(true)
    setError(null)
    try {
      let result
      if (lane === 'local') {
        const request = localContinuationRequest(run, selected)
        if (!request) throw new Error('This local checkpoint could not be addressed.')
        result = await postWithConfirmations(body => postJson(request.url, body), request.body, 'Continue anyway (force)')
      } else result = await cloud.submit(run, selected)
      const outcome = continueAttemptOutcome({ response: result, declined: result == null })
      if (outcome.close) {
        targetRef.current = null
        setTarget(null)
        toast.success('Continuation started.')
        await poll()
      } else setError(outcome.error)
    } catch (thrown) { setError(continueAttemptOutcome({ thrown }).error) }
    finally { busyRef.current = false; setBusy(false) }
  }
  return {
    canContinueRun, continueRun: run => open(run), continueFromCheckpoint,
    continuing: target ? { [target.run_id ?? target.record_id]: busy } : {},
    dialog: target ? { target, where: target.source === 'cloud' ? 'cloud' : 'local',
      checkpoints: target.resume_checkpoints?.length ? target.resume_checkpoints : (target.resume_steps || []).map(step => ({ step })),
      initialFromStep: initialStep, lanes, transportPlan, busy, error, onResolve: submitContinue,
      settings: { optimizer: target.settings?.optimizer, learning_rate: target.settings?.lr } } : null,
  }
}
