import { NavLink } from 'react-router'
import { Clapperboard } from 'lucide-react'
import { laneTabClass } from '@lds/plugin-sdk/bank';

/** The 🎬 Video tab of the Bank's lane switch — the `lanes` slot, on both bank
 *  pages (the core's Image Bank and this plugin's Video Bank).
 *
 *  WHY A SWITCH AND NOT A SIXTH NAV ITEM: the desktop bar already carries five
 *  workspaces and overflows at exactly 768 px; and these are not two
 *  workspaces but one job — "triage a folder before it becomes a dataset" —
 *  over two kinds of material. Two routes, two sets of components, because a
 *  video bank cuts one file into hundreds of shots, stores bounds rather than
 *  files, and encodes only at promotion. */
export default function VideoLaneTab() {
  return (
    <NavLink to="/video-bank" className={laneTabClass}>
      <Clapperboard aria-hidden="true" className="h-3.5 w-3.5" /> Video
      <span className="ml-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400">
        Beta
      </span>
    </NavLink>
  )
}
