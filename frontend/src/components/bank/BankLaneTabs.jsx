import { NavLink } from 'react-router'
import { Images } from 'lucide-react'
import PluginSlot from '../../plugins/PluginSlot.jsx'

export const laneTabClass = ({ isActive }) => [
    'rounded-full border px-3 py-1 text-xs font-semibold no-underline transition-colors',
    isActive
      ? 'border-primary/60 bg-primary/15 text-content'
      : 'border-border bg-surface text-content-muted hover:bg-surface-raised hover:text-content',
  ].join(' ')

export default function BankLaneTabs({ className = '', surface = 'bank' }) {
  return (
    <div role="group" aria-label="Kind of bank" className={`flex flex-wrap items-center gap-1.5 ${className}`}>
      <span className="mr-1 font-mono text-[11px] uppercase tracking-[0.18em] text-content-subtle">bank of</span>
      <NavLink to="/bank" end className={laneTabClass}>
        <Images aria-hidden="true" className="h-3.5 w-3.5" /> Images
      </NavLink>
      <PluginSlot slot="lanes" surface={surface} />
    </div>
  )
}
