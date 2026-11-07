import { Link, useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'
import { useSetupJourney, saveSetupJourney } from './useSetupJourney'
import { journeyPath, SETUP_GOALS } from './setupJourney'

export default function SetupJourneyNotice() {
  const journey = useSetupJourney()
  const location = useLocation()
  const navigate = useNavigate()
  if (!journey || (location.pathname === '/setup' && !new URLSearchParams(location.search).has('step'))) return null
  function closeGuide() {
    saveSetupJourney(null)
    if (location.pathname === '/setup') {
      const params = new URLSearchParams(location.search)
      for (const key of ['goal', 'plugin', 'engine', 'capability']) params.delete(key)
      navigate('/setup?' + params, { replace: true })
    }
  }
  return <aside aria-label="Your setup plan" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-primary/40 bg-surface px-4 py-2 text-sm" data-probe-reading="setup-journey-return">
    <Link to={journeyPath(journey)} className="inline-flex min-h-10 items-center gap-2 text-primary hover:underline">
      <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden="true" /> Back to my setup plan
    </Link>
    <span className="text-content-muted">{SETUP_GOALS.find(goal => goal.id === journey.goal)?.title}</span>
    <button type="button" onClick={closeGuide} className="min-h-10 text-xs text-content-muted underline">Close guide</button>
  </aside>
}
